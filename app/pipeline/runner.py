"""Pipeline runner — orchestrates the full ad generation flow.

Reads configuration from the Campaign model, runs each pipeline stage,
updates the AdRun status at each step.
"""

import logging
import os
from datetime import datetime, timezone

from app.extensions import db
from app.models import AdRun, Campaign
from app.pipeline.feeds import get_feed
from app.pipeline.script_gen import generate_script
from app.pipeline.voiceover import generate_voiceover
from app.pipeline.mixer import mix_audio
from app.pipeline.exceptions import PipelineError

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
        # 1. Fetch feed data
        _update_status(ad_run, "fetching_data")
        feed = get_feed(campaign.feed_type)
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

        # 4. Generate voiceover
        _update_status(ad_run, "generating_voiceover")
        voice_id = campaign.effective_voice_id
        vo_bytes = generate_voiceover(script, voice_id)

        # 5. Mix with music bed
        _update_status(ad_run, "mixing")
        music_bytes = _get_music_bed(campaign)
        final_bytes = mix_audio(
            music_bed_bytes=music_bytes,
            voiceover_bytes=vo_bytes,
            intro_seconds=campaign.intro_seconds,
            outro_seconds=campaign.outro_seconds,
            duck_volume=campaign.duck_volume,
            duck_fade=campaign.duck_fade,
        )

        # 6. Save outputs
        _update_status(ad_run, "uploading")
        _save_outputs(ad_run, vo_bytes, final_bytes)

        # 7. Deliver to Frequency (if enabled and app ID is set for this campaign)
        if campaign.delivery_enabled and campaign.frequency_app_id:
            from app.delivery.frequency import (
                deliver_ad,
                is_delivery_available,
                FrequencyDeliveryError,
                FrequencyNotConfiguredError,
            )
            if is_delivery_available():
                _update_status(ad_run, "delivering")
                try:
                    vast_xml = deliver_ad(ad_run, final_bytes)
                    ad_run.vast_response = vast_xml
                    ad_run.delivered_at = datetime.now(timezone.utc)
                    ad_run.delivery_reference = "frequency"
                    db.session.commit()
                    logger.info("Delivered to Frequency for run #%d", ad_run.id)
                except (FrequencyDeliveryError, FrequencyNotConfiguredError) as exc:
                    ad_run.delivery_error = str(exc)
                    db.session.commit()
                    logger.error("Frequency delivery failed for run #%d: %s", ad_run.id, exc)

        # 8. Done
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

    return {
        **feed_data,
        "advertiser_name": advertiser.name,
        "advertiser_description": advertiser.description or "",
        "advertiser_tagline": advertiser.tagline or "",
        "advertiser_cta": campaign.cta or "",
        "seasonal_hook": campaign.seasonal_hook or "",
        "target_city": campaign.target_city or "",
        "target_seconds": campaign.target_seconds,
        "target_words": campaign.target_words,
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
