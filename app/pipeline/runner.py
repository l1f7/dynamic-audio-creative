"""Pipeline runner — orchestrates the full ad generation flow.

Reads configuration from the Campaign model, runs each pipeline stage,
updates the AdRun status at each step.
"""

import logging
import os
import random
from datetime import datetime, timezone

from app.delivery.targets import deliver_run
from app.extensions import db
from app.models import AdRun, Campaign
from app.models.ad_run import (
    DELIVERY_FAILED,
    STATUS_COMPLETE,
    STATUS_DELIVERING,
    STATUS_FAILED,
)
from app.models.delivery_attempt import TARGET_DV360, TARGET_FREQUENCY
from app.pipeline.feeds import get_feed
from app.pipeline.script_gen import generate_script
from app.pipeline.voiceover import generate_voiceover
from app.pipeline.mixer import mix_audio
from app.pipeline.exceptions import FeedFetchError, PipelineError, PushCampaignError

logger = logging.getLogger(__name__)


def _requested_targets(deliver_frequency: bool, deliver_dv360: bool) -> list[str]:
    """Which ad servers the admin ticked on the rerun/redeliver form."""
    chosen = []
    if deliver_frequency:
        chosen.append(TARGET_FREQUENCY)
    if deliver_dv360:
        chosen.append(TARGET_DV360)
    return chosen


def _settle_run(ad_run: AdRun) -> None:
    """Give the run its terminal status once delivery has been attempted.

    The audio can be perfect and still reach nobody. Every path used to set
    "complete" here regardless, so a run both ad servers rejected showed a
    green Complete badge — the failure lived only in a delivery error field
    that nothing surfaced. A run where every attempted target failed is a
    failed run, which is what the pushed-file path has always done.
    """
    if ad_run.delivery_state == DELIVERY_FAILED:
        ad_run.status = STATUS_FAILED
        ad_run.error_message = "; ".join(ad_run.delivery_errors)
    else:
        ad_run.status = STATUS_COMPLETE
    ad_run.completed_at = datetime.now(timezone.utc)


def run_pipeline(campaign_id: int, triggered_by: str = "manual") -> AdRun:
    """Execute the full pipeline for a campaign.

    Args:
        campaign_id: The campaign to generate an ad for.
        triggered_by: "manual", "cron", or "api".

    Returns:
        The AdRun instance (complete or failed).

    Raises:
        PushCampaignError: the campaign receives creative from the drop app.
    """
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.is_push:
        # Every caller is expected to check first; this is the backstop that
        # keeps a push campaign's delivered creative from being overwritten
        # by a generated one. No AdRun is created.
        raise PushCampaignError(
            f"Campaign {campaign_id} is a push campaign — creative comes from the drop app"
        )

    # Create the run record
    ad_run = AdRun(
        campaign_id=campaign_id,
        triggered_by=triggered_by,
        status="pending",
    )
    db.session.add(ad_run)
    db.session.commit()

    try:
        # 1. Fetch feed data + generate script (fallback if feed fails or is empty),
        # unless a manual override script is staged for this run.
        if campaign.use_manual_override and (campaign.manual_override_script or "").strip():
            logger.info(
                "Run #%d: manual override armed — using staged script, skipping feed fetch",
                ad_run.id,
            )
            script = campaign.manual_override_script
            ad_run.script_text = script
            ad_run.script_source = "manual_override"
            db.session.commit()
        else:
            _update_status(ad_run, "fetching_data")
            feed = get_feed(campaign.feed_type)
            try:
                feed_data = feed.fetch(campaign)
                ad_run.feed_data_snapshot = feed_data
                db.session.commit()

                # 2. Build template vars
                template_vars = _build_template_vars(campaign, feed_data)

                # 3. Generate script
                _update_status(ad_run, "generating_script")
                prompt_template = campaign.prompt_template or feed.default_prompt_template()
                script = generate_script(prompt_template, template_vars)
                ad_run.script_text = script
                ad_run.script_source = "feed"
                db.session.commit()

            except FeedFetchError as exc:
                if not campaign.fallback_script:
                    raise
                logger.warning(
                    "Run #%d: feed failed (%s) — using fallback script", ad_run.id, exc
                )
                script = campaign.fallback_script
                ad_run.script_text = script
                ad_run.script_source = "fallback"
                db.session.commit()

        # 4. Generate voiceover
        _update_status(ad_run, "generating_voiceover")
        voice_id = campaign.effective_voice_id
        is_custom = bool((campaign.voice_custom_id or "").strip())
        logger.info("Using voice: preset=%s custom=%s resolved_id=%s",
                    campaign.voice_preset, campaign.voice_custom_id, voice_id)
        if not voice_id:
            raise PipelineError("No voice ID resolved — check campaign voice settings.")
        vo_bytes = generate_voiceover(script, voice_id, is_custom=is_custom)

        # 5. Mix with music bed
        _update_status(ad_run, "mixing")
        music_bytes = _get_music_bed(campaign)
        final_bytes, stretch_factor = mix_audio(
            music_bed_bytes=music_bytes,
            voiceover_bytes=vo_bytes,
            intro_seconds=campaign.intro_seconds,
            outro_seconds=campaign.outro_seconds,
            duck_volume=campaign.duck_volume,
            duck_fade=campaign.duck_fade,
            target_seconds=campaign.target_seconds,
        )
        ad_run.stretch_factor = stretch_factor

        # 6. Save outputs
        _update_status(ad_run, "uploading")
        _save_outputs(ad_run, vo_bytes, final_bytes)
        del vo_bytes, music_bytes  # free intermediate buffers before delivery

        # 7. Deliver to every ad server configured for this campaign
        deliver_run(
            ad_run, final_bytes,
            on_first_attempt=lambda: _update_status(ad_run, STATUS_DELIVERING),
        )
        # 9. Done
        _settle_run(ad_run)
        # One-shot: consume the override only on success, so a failed run
        # leaves it armed and a retry still uses the staged script.
        if ad_run.status == STATUS_COMPLETE and ad_run.script_source == "manual_override":
            campaign.use_manual_override = False
        db.session.commit()

        logger.info("Pipeline complete for run #%d", ad_run.id)

    except PipelineError as exc:
        ad_run.status = STATUS_FAILED
        ad_run.error_message = str(exc)
        ad_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Pipeline failed for run #%d: %s", ad_run.id, exc)

    except Exception as exc:
        ad_run.status = STATUS_FAILED
        ad_run.error_message = f"Unexpected error: {exc}"
        ad_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.exception("Unexpected pipeline error for run #%d", ad_run.id)

    return ad_run


def rerun_from_script(source_run_id: int, script: str, deliver_frequency: bool = True, deliver_dv360: bool = True) -> AdRun:
    """Create a new run from an edited script, then voiceover → mix → deliver.

    Copies the feed snapshot and campaign settings from the source run.
    Returns the new AdRun.
    """
    source = db.session.get(AdRun, source_run_id)
    if not source:
        raise ValueError(f"Run {source_run_id} not found")
    campaign = source.campaign

    new_run = AdRun(
        campaign_id=campaign.id,
        triggered_by="manual",
        status="pending",
        script_text=script,
        feed_data_snapshot=source.feed_data_snapshot,
    )
    db.session.add(new_run)
    db.session.commit()

    try:
        _update_status(new_run, "generating_voiceover")
        voice_id = campaign.effective_voice_id
        is_custom = bool((campaign.voice_custom_id or "").strip())
        logger.info("Rerun #%d (from #%d) using voice: preset=%s custom=%s resolved_id=%s",
                    new_run.id, source_run_id, campaign.voice_preset, campaign.voice_custom_id, voice_id)
        if not voice_id:
            raise PipelineError("No voice ID resolved — check campaign voice settings.")
        vo_bytes = generate_voiceover(script, voice_id, is_custom=is_custom)

        _update_status(new_run, "mixing")
        music_bytes = _get_music_bed(campaign)
        final_bytes, stretch_factor = mix_audio(
            music_bed_bytes=music_bytes,
            voiceover_bytes=vo_bytes,
            intro_seconds=campaign.intro_seconds,
            outro_seconds=campaign.outro_seconds,
            duck_volume=campaign.duck_volume,
            duck_fade=campaign.duck_fade,
            target_seconds=campaign.target_seconds,
        )
        new_run.stretch_factor = stretch_factor

        _update_status(new_run, "uploading")
        _save_outputs(new_run, vo_bytes, final_bytes)
        del vo_bytes, music_bytes  # free intermediate buffers before delivery

        deliver_run(
            new_run, final_bytes,
            only=_requested_targets(deliver_frequency, deliver_dv360),
            on_first_attempt=lambda: _update_status(new_run, STATUS_DELIVERING),
        )

        _settle_run(new_run)
        db.session.commit()
        logger.info(
            "Rerun finished — new run #%d (source #%d) status=%s delivery=%s",
            new_run.id, source_run_id, new_run.status, new_run.delivery_state,
        )

    except PipelineError as exc:
        new_run.status = STATUS_FAILED
        new_run.error_message = str(exc)
        new_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Rerun failed for new run #%d: %s", new_run.id, exc)

    except Exception as exc:
        new_run.status = STATUS_FAILED
        new_run.error_message = f"Unexpected error: {exc}"
        new_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.exception("Unexpected rerun error for new run #%d", new_run.id)

    return new_run


def redeliver(run_id: int, deliver_frequency: bool = False, deliver_dv360: bool = False) -> AdRun:
    """Re-deliver an existing completed run's audio to Frequency and/or DV360.

    Does not regenerate voiceover or remix — just re-submits the final ad.
    """
    ad_run = db.session.get(AdRun, run_id)
    if not ad_run:
        raise ValueError(f"Run {run_id} not found")
    if not ad_run.final_ad_s3_key:
        raise PipelineError(f"Run {run_id} has no final audio to deliver")

    campaign = ad_run.campaign

    # Load the final ad bytes
    final_bytes = _load_final_ad(ad_run)

    deliver_run(
        ad_run, final_bytes,
        only=_requested_targets(deliver_frequency, deliver_dv360),
        on_first_attempt=lambda: _update_status(ad_run, STATUS_DELIVERING),
    )

    _settle_run(ad_run)
    db.session.commit()
    logger.info(
        "Redelivery finished for run #%d — status=%s delivery=%s",
        ad_run.id, ad_run.status, ad_run.delivery_state,
    )

    return ad_run


def _load_final_ad(ad_run: AdRun) -> bytes:
    """Load the final ad audio bytes from S3 or local file."""
    key = ad_run.final_ad_s3_key

    # Local file (dev)
    if os.path.isfile(key):
        with open(key, "rb") as f:
            return f.read()

    # S3
    try:
        from app.storage import s3
        return s3.download(key)
    except Exception as exc:
        raise PipelineError(f"Failed to load final ad audio: {exc}") from exc


def _update_status(ad_run: AdRun, status: str):
    """Update run status and commit."""
    ad_run.status = status
    db.session.commit()
    logger.info("Run #%d: %s", ad_run.id, status)


def _build_template_vars(campaign: Campaign, feed_data: dict) -> dict:
    """Merge feed data with campaign/advertiser config for the prompt template."""
    advertiser = campaign.advertiser

    # Build pronunciation section
    pron_entries = campaign.pronunciation_entries
    if pron_entries:
        guide_lines = [
            f'- "{e.written_form}" → write as "{e.spoken_form}"'
            for e in pron_entries
        ]
        pronunciation_section = (
            "PRONUNCIATION (use these exact spellings so text-to-speech "
            "reads them correctly):\n"
            + "\n".join(guide_lines)
            + "\n\n"
        )
        pronunciation_instruction = (
            "- Use the pronunciation spellings above whenever those words appear\n"
        )
    else:
        pronunciation_section = ""
        pronunciation_instruction = ""

    # Pick one ad tag at random (if any are configured)
    tags = campaign.ad_tags or []
    if len(tags) > 1:
        ad_tag = random.SystemRandom().choice(tags)
        logger.info("Ad tag selected: %r (index %d of %d)", ad_tag, tags.index(ad_tag), len(tags))
    elif tags:
        ad_tag = tags[0]
    else:
        ad_tag = ""
    tag_words = len(ad_tag.split()) if ad_tag else 0
    body_words = max(10, campaign.target_words - tag_words)

    secs = campaign.target_seconds
    if secs <= 20:
        fixture_mention_guidance = "No time for more — go straight to the transition"
    elif secs <= 30:
        fixture_mention_guidance = "Briefly mention one more result if it fits naturally"
    elif secs <= 45:
        fixture_mention_guidance = "Mention 1-2 more matches or a top-scorer highlight if time allows"
    else:
        fixture_mention_guidance = "Mention 2-3 more matches and a top-scorer highlight"

    return {
        **feed_data,
        "advertiser_name": advertiser.name,
        "advertiser_description": advertiser.description or "",
        "advertiser_tagline": advertiser.tagline or "",
        "advertiser_cta": campaign.cta or "",
        "seasonal_hook": campaign.seasonal_hook or "",
        "target_city": campaign.target_city or "",
        "target_seconds": secs,
        "target_words": campaign.target_words,
        "body_words": body_words,
        "fixture_mention_guidance": fixture_mention_guidance,
        "ad_tag": ad_tag,
        "pronunciation_section": pronunciation_section,
        "pronunciation_instruction": pronunciation_instruction,
    }


def _get_music_bed(campaign: Campaign) -> bytes:
    """Load the music bed bytes — from S3 if configured, else local file."""
    if campaign.music_bed_s3_key:
        # S3 storage
        try:
            from app.storage import s3
            return s3.download(campaign.music_bed_s3_key)
        except Exception as exc:
            raise PipelineError(f"Failed to download music bed from S3: {exc}") from exc

    # Local file fallback for development
    local_path = campaign.music_bed_filename
    if local_path and os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            return f.read()

    raise PipelineError(
        "No music bed configured for this campaign. "
        "Upload one in the campaign settings."
    )


def _save_outputs(ad_run: AdRun, vo_bytes: bytes, final_bytes: bytes):
    """Save generated audio — to S3 if configured, else local files."""
    from flask import current_app

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Try S3 first
    if current_app.config.get("S3_ENDPOINT_URL"):
        from app.storage import s3

        vo_key = f"campaigns/{ad_run.campaign_id}/runs/{ad_run.id}/voiceover_{ts}.mp3"
        final_key = f"campaigns/{ad_run.campaign_id}/runs/{ad_run.id}/final_ad_{ts}.mp3"

        s3.upload(vo_key, vo_bytes)
        s3.upload(final_key, final_bytes)

        ad_run.voiceover_s3_key = vo_key
        ad_run.final_ad_s3_key = final_key
        logger.info("Outputs uploaded to S3")

    else:
        # Local file fallback for development
        output_dir = os.path.join(
            current_app.instance_path, "generated", str(ad_run.campaign_id)
        )
        os.makedirs(output_dir, exist_ok=True)

        vo_path = os.path.join(output_dir, f"voiceover_{ad_run.id}_{ts}.mp3")
        final_path = os.path.join(output_dir, f"final_ad_{ad_run.id}_{ts}.mp3")

        with open(vo_path, "wb") as f:
            f.write(vo_bytes)
        with open(final_path, "wb") as f:
            f.write(final_bytes)

        # Store local paths in the S3 key fields (they'll work for dev)
        ad_run.voiceover_s3_key = vo_path
        ad_run.final_ad_s3_key = final_path
        logger.info("Outputs saved locally: %s", output_dir)
