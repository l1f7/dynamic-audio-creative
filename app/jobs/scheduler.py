"""Cron scheduler — fires due pipelines and delivers pushed files.

Both entry points are plain functions so a queue worker could call them
unchanged if one is ever added.
"""

import logging
from datetime import datetime, timezone, timedelta

from croniter import croniter

from app.extensions import db
from app.models import Campaign, AdRun
from app.models.ad_run import (
    DELIVERY_DELIVERED,
    STATUS_COMPLETE,
    STATUS_DELIVERING,
    STATUS_FAILED,
    STATUS_PENDING,
    TERMINAL_STATUSES,
    TRIGGER_WATCHER,
)
from app.models.delivery_attempt import TARGET_FREQUENCY
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
        if campaign.is_push:
            continue  # creative arrives from the drop app; nothing to generate
        if not campaign.cron_schedule:
            continue

        # Anchor to the last finished run (any trigger) so missed ticks
        # are caught on the next scheduler invocation.
        last_run = (
            AdRun.query
            .filter_by(campaign_id=campaign.id)
            .filter(AdRun.status.in_(TERMINAL_STATUSES))
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
            .filter(~AdRun.status.in_(TERMINAL_STATUSES))
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


# ---------------------------------------------------------------------------
# Pushed files
# ---------------------------------------------------------------------------


def deliver_pending_pushes() -> int:
    """Deliver every pending pushed run whose campaign is not paused. Returns the count."""
    from app.delivery.frequency import is_delivery_available

    if not is_delivery_available():
        logger.warning("[Push] Frequency delivery not available — leaving pushed runs pending")
        return 0

    runs = _pending_pushed_runs()
    for run in runs:
        _deliver_pushed_run(run)
    return len(runs)


def _pending_pushed_runs() -> list:
    return (
        AdRun.query.join(Campaign)
        .filter(
            AdRun.triggered_by == TRIGGER_WATCHER,
            AdRun.status == STATUS_PENDING,
            Campaign.delivery_enabled.is_(True),
        )
        .order_by(AdRun.created_at)
        .all()
    )


def _deliver_pushed_run(run: AdRun) -> None:
    """Hand a pushed file to Frequency. DV360 is never a target for these."""
    from app.delivery.targets import deliver_run
    from app.pipeline.runner import _load_final_ad

    # Claim the run first so a slow tick overlapping the next cannot deliver twice
    run.status = STATUS_DELIVERING
    db.session.commit()

    try:
        audio = _load_final_ad(run)
    except Exception as exc:
        _mark_pushed_run_failed(run, exc)
        return

    deliver_run(run, audio, only=[TARGET_FREQUENCY])
    _settle_pushed_run(run)


def _settle_pushed_run(run: AdRun) -> None:
    """Terminal status for a pushed run, from what the ad server actually did."""
    run.completed_at = datetime.now(timezone.utc)
    if run.delivery_state == DELIVERY_DELIVERED:
        run.status = STATUS_COMPLETE
        run.error_message = None
        logger.info("[Push] Delivered run #%d", run.id)
    else:
        run.status = STATUS_FAILED
        run.error_message = "; ".join(run.delivery_errors)
        logger.error("[Push] Delivery failed for run #%d: %s", run.id, run.error_message)
    db.session.commit()


def _mark_pushed_run_failed(run: AdRun, exc: Exception) -> None:
    """Failure before any ad server was reached — e.g. the audio would not load."""
    run.record_delivery(TARGET_FREQUENCY, False, error=str(exc))
    run.error_message = str(exc)
    run.completed_at = datetime.now(timezone.utc)
    run.status = STATUS_FAILED
    db.session.commit()
    logger.error("[Push] Delivery failed for run #%d: %s", run.id, exc)
