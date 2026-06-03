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

    Intended to be called every minute. A campaign is considered due if its
    most recent cron tick falls within the last 60 seconds and it has no
    run already in progress.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=60)

    campaigns = Campaign.query.filter_by(is_active=True).all()
    due = []

    for campaign in campaigns:
        if not campaign.cron_schedule:
            continue

        try:
            cron = croniter(campaign.cron_schedule, window_start)
            next_tick = cron.get_next(datetime)
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
