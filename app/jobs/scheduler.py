"""Cron scheduler — finds campaigns due to run and fires the pipeline."""

import logging
from datetime import datetime, timezone, timedelta

from croniter import croniter

from app.extensions import db
from app.models import Campaign, AdRun
from app.pipeline.runner import run_pipeline

logger = logging.getLogger(__name__)


def run_due_campaigns():
    """Check all active campaigns and run any whose cron schedule is due.

    Intended to be called periodically (e.g. every minute via Render cron).
    A campaign is due if its next cron tick after the last finished run is
    in the past.  This is resilient to scheduler jitter or slow cold-boots
    because it anchors to persistent state rather than a fixed time window.
    """
    now = datetime.now(timezone.utc)

    campaigns = Campaign.query.filter_by(is_active=True).all()
    due = []

    for campaign in campaigns:
        if not campaign.cron_schedule:
            continue

        # Anchor to the last finished run (any trigger) so missed ticks
        # are caught on the next scheduler invocation.
        last_run = (
            AdRun.query
            .filter_by(campaign_id=campaign.id)
            .filter(AdRun.status.in_(["complete", "failed"]))
            .order_by(AdRun.created_at.desc())
            .first()
        )
        if last_run and last_run.created_at:
            base_time = last_run.created_at
            # DB may return naive datetime — ensure UTC-aware for croniter
            if base_time.tzinfo is None:
                base_time = base_time.replace(tzinfo=timezone.utc)
        else:
            # Never run before — look back 24 h so the first tick is caught
            base_time = now - timedelta(hours=24)

        try:
            cron = croniter(campaign.cron_schedule, base_time)
            next_tick = cron.get_next(datetime)
            # Ensure aware for comparison with `now`
            if next_tick.tzinfo is None:
                next_tick = next_tick.replace(tzinfo=timezone.utc)
        except Exception:
            logger.warning(
                "Campaign %d has invalid cron_schedule %r — skipping",
                campaign.id,
                campaign.cron_schedule,
            )
            continue

        if next_tick > now:
            continue  # not due yet

        # Skip if a run is already in progress for this campaign
        in_progress = (
            AdRun.query
            .filter_by(campaign_id=campaign.id)
            .filter(~AdRun.status.in_(["complete", "failed"]))
            .first()
        )
        if in_progress:
            logger.info(
                "Campaign %d (%s): run #%d already in progress — skipping",
                campaign.id,
                campaign.name,
                in_progress.id,
            )
            continue

        due.append(campaign)

    if not due:
        logger.info("No campaigns due at %s", now.isoformat())
        return

    for campaign in due:
        logger.info(
            "Campaign %d (%s): triggering cron run", campaign.id, campaign.name
        )
        try:
            ad_run = run_pipeline(campaign.id, triggered_by="cron")
            logger.info(
                "Campaign %d: run #%d finished with status=%s",
                campaign.id,
                ad_run.id,
                ad_run.status,
            )
        except Exception:
            logger.exception("Campaign %d: unexpected error in run_pipeline", campaign.id)
