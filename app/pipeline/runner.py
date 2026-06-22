"""Pipeline runner — orchestrates the full ad generation flow.

Reads configuration from the Campaign model, runs each pipeline stage,
updates the AdRun status at each step.
"""

import logging
import os
import random
from datetime import datetime, timezone

from app.extensions import db
from app.models import AdRun, Campaign
from app.pipeline.feeds import get_feed
from app.pipeline.script_gen import generate_script
from app.pipeline.voiceover import generate_voiceover
from app.pipeline.mixer import mix_audio
from app.pipeline.exceptions import FeedFetchError, PipelineError

logger = logging.getLogger(__name__)


def run_pipeline(campaign_id: int, triggered_by: str = "manual") -> AdRun:
    """Execute the full pipeline for a campaign.

    Args:
        campaign_id: The campaign to generate an ad for.
        triggered_by: "manual", "cron", or "api".

    Returns:
        The AdRun instance (complete or failed).
    """
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    # Create the run record
    ad_run = AdRun(
        campaign_id=campaign_id,
        triggered_by=triggered_by,
        status="pending",
    )
    db.session.add(ad_run)
    db.session.commit()

    try:
        # 1. Fetch feed data + generate script (fallback if feed fails or is empty)
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
            db.session.commit()

        except FeedFetchError as exc:
            if not campaign.fallback_script:
                raise
            logger.warning(
                "Run #%d: feed failed (%s) — using fallback script", ad_run.id, exc
            )
            script = campaign.fallback_script
            ad_run.script_text = script
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

        # 7. Deliver to Frequency (if enabled and app ID is set for this campaign)
        if not campaign.delivery_enabled:
            logger.warning("[Frequency] SKIP run #%d — delivery_enabled=False on campaign '%s'",
                           ad_run.id, campaign.name)
        elif not campaign.frequency_app_id:
            logger.warning("[Frequency] SKIP run #%d — no frequency_app_id on campaign '%s'",
                           ad_run.id, campaign.name)
        else:
            from app.delivery.frequency import (
                deliver_ad,
                is_delivery_available,
                FrequencyDeliveryError,
                FrequencyNotConfiguredError,
            )
            from flask import current_app
            cfg = current_app.config
            freq_enabled = cfg.get("FREQUENCY_ENABLED")
            base_url = cfg.get("CMPAPI_BASE_URL")
            logger.info("[Frequency] config check — FREQUENCY_ENABLED=%s  CMPAPI_BASE_URL=%s",
                        freq_enabled, base_url or "(not set)")
            if not is_delivery_available():
                logger.warning(
                    "[Frequency] SKIP run #%d — delivery not available "
                    "(FREQUENCY_ENABLED=%s, CMPAPI_BASE_URL=%s)",
                    ad_run.id, freq_enabled, base_url or "(not set)",
                )
            else:
                _update_status(ad_run, "delivering")
                try:
                    vast_xml = deliver_ad(ad_run, final_bytes)
                    ad_run.vast_response = vast_xml
                    ad_run.delivered_at = datetime.now(timezone.utc)
                    ad_run.delivery_reference = "frequency"
                    db.session.commit()
                    logger.info("[Frequency] Delivered successfully for run #%d", ad_run.id)
                except (FrequencyDeliveryError, FrequencyNotConfiguredError) as exc:
                    ad_run.delivery_error = str(exc)
                    db.session.commit()
                    logger.error("[Frequency] Delivery FAILED for run #%d: %s", ad_run.id, exc)

        # 8. Deliver to DV360 (if enabled)
        if not campaign.dv360_enabled:
            logger.info("[DV360] SKIP run #%d — dv360_enabled=False on campaign '%s'",
                        ad_run.id, campaign.name)
        elif not campaign.dv360_line_item_id:
            logger.warning("[DV360] SKIP run #%d — no dv360_line_item_id on campaign '%s'",
                           ad_run.id, campaign.name)
        else:
            from app.delivery.dv360 import (
                deliver_ad as dv360_deliver_ad,
                is_delivery_available as dv360_available,
                DV360DeliveryError,
                DV360NotConfiguredError,
            )
            from flask import current_app as _app
            logger.info("[DV360] config check — DV360_ENABLED=%s",
                        _app.config.get("DV360_ENABLED"))
            if not dv360_available():
                logger.warning(
                    "[DV360] SKIP run #%d — DV360_ENABLED is not set to true",
                    ad_run.id,
                )
            else:
                _update_status(ad_run, "delivering")
                try:
                    creative_name = dv360_deliver_ad(ad_run, final_bytes)
                    ad_run.dv360_delivered_at = datetime.now(timezone.utc)
                    ad_run.dv360_creative_name = creative_name
                    db.session.commit()
                    logger.info("[DV360] Delivered successfully for run #%d — %s",
                                ad_run.id, creative_name)
                except (DV360DeliveryError, DV360NotConfiguredError) as exc:
                    ad_run.dv360_delivery_error = str(exc)
                    db.session.commit()
                    logger.error("[DV360] Delivery FAILED for run #%d: %s", ad_run.id, exc)

        # 9. Done
        ad_run.status = "complete"
        ad_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info("Pipeline complete for run #%d", ad_run.id)

    except PipelineError as exc:
        ad_run.status = "failed"
        ad_run.error_message = str(exc)
        ad_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Pipeline failed for run #%d: %s", ad_run.id, exc)

    except Exception as exc:
        ad_run.status = "failed"
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

        # Deliver to Frequency if configured and requested
        if not deliver_frequency:
            logger.info("[Frequency] SKIP rerun #%d — unchecked by user", new_run.id)
        elif campaign.delivery_enabled and campaign.frequency_app_id:
            from app.delivery.frequency import (
                deliver_ad,
                is_delivery_available,
                FrequencyDeliveryError,
                FrequencyNotConfiguredError,
            )
            if is_delivery_available():
                _update_status(new_run, "delivering")
                try:
                    vast_xml = deliver_ad(new_run, final_bytes)
                    new_run.vast_response = vast_xml
                    new_run.delivered_at = datetime.now(timezone.utc)
                    new_run.delivery_reference = "frequency"
                    db.session.commit()
                    logger.info("[Frequency] Delivered for rerun #%d", new_run.id)
                except (FrequencyDeliveryError, FrequencyNotConfiguredError) as exc:
                    new_run.delivery_error = str(exc)
                    db.session.commit()
                    logger.error("[Frequency] Delivery failed for rerun #%d: %s", new_run.id, exc)

        # Deliver to DV360 if configured and requested
        if not deliver_dv360:
            logger.info("[DV360] SKIP rerun #%d — unchecked by user", new_run.id)
        elif campaign.dv360_enabled and campaign.dv360_line_item_id:
            from app.delivery.dv360 import (
                deliver_ad as dv360_deliver_ad,
                is_delivery_available as dv360_available,
                DV360DeliveryError,
                DV360NotConfiguredError,
            )
            if dv360_available():
                _update_status(new_run, "delivering")
                try:
                    creative_name = dv360_deliver_ad(new_run, final_bytes)
                    new_run.dv360_delivered_at = datetime.now(timezone.utc)
                    new_run.dv360_creative_name = creative_name
                    db.session.commit()
                    logger.info("[DV360] Delivered for rerun #%d — %s", new_run.id, creative_name)
                except (DV360DeliveryError, DV360NotConfiguredError) as exc:
                    new_run.dv360_delivery_error = str(exc)
                    db.session.commit()
                    logger.error("[DV360] Delivery failed for rerun #%d: %s", new_run.id, exc)

        new_run.status = "complete"
        new_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("Rerun complete — new run #%d (source #%d)", new_run.id, source_run_id)

    except PipelineError as exc:
        new_run.status = "failed"
        new_run.error_message = str(exc)
        new_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.error("Rerun failed for new run #%d: %s", new_run.id, exc)

    except Exception as exc:
        new_run.status = "failed"
        new_run.error_message = f"Unexpected error: {exc}"
        new_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.exception("Unexpected rerun error for new run #%d", new_run.id)

    return new_run


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
