"""Register pushed files as runs. Delivery happens on the scheduler tick."""

import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.delivery import frequency_token
from app.extensions import db
from app.models import AdRun, Campaign, DeliveryAttempt
from app.models.delivery_attempt import TARGET_FREQUENCY
from app.models.ad_run import (
    STATUS_FAILED,
    STATUS_PENDING,
    TRIGGER_WATCHER,
)
from app.push import audio
from app.storage import s3

logger = logging.getLogger(__name__)

UPLOAD_PREFIX = "pushed"
UPLOAD_URL_TTL_SECONDS = 30 * 60  # matches the daemon's allowance for the PUT
DEFAULT_SUFFIX = ".bin"
MP3_SUFFIX = ".mp3"

# ---------------------------------------------------------------------------
# Keys and lookups
# ---------------------------------------------------------------------------


def upload_key_for(campaign: Campaign, content_hash: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or DEFAULT_SUFFIX
    return f"{UPLOAD_PREFIX}/{campaign.id}/{content_hash}{suffix}"


def owns_upload_key(campaign: Campaign, content_hash: str, upload_key: str) -> bool:
    return upload_key.startswith(f"{UPLOAD_PREFIX}/{campaign.id}/{content_hash}")


def find_run(campaign: Campaign, content_hash: str) -> AdRun | None:
    return campaign.ad_runs.filter(AdRun.source_content_hash == content_hash).first()


def find_delivered_run(campaign: Campaign, content_hash: str) -> AdRun | None:
    run = find_run(campaign, content_hash)
    if run and run.delivered_at is not None:
        return run
    return None


def active_run_id(campaign: Campaign) -> int | None:
    """The run whose creative DAC believes is live.

    Frequency has no "which creative is live" endpoint, so this is DAC's own
    record: the most recent run whose latest Frequency attempt succeeded.
    Joined against delivery_attempts, which replaced the old delivered_at
    column — a run can now have several attempts, and only the last counts.
    """
    latest = (
        campaign.ad_runs
        .join(AdRun.delivery_attempts)
        .filter(
            DeliveryAttempt.target == TARGET_FREQUENCY,
            DeliveryAttempt.succeeded.is_(True),
        )
        .order_by(DeliveryAttempt.attempted_at.desc())
        .first()
    )
    # A later failed attempt supersedes an earlier success.
    return latest.id if latest and latest.delivered_at else None


def is_deliverable(campaign: Campaign) -> bool:
    """Whether Frequency could take this campaign's creative.

    Asks the Frequency target so there is one definition of this. Ignores
    delivery_enabled: that is a pause switch, not a configuration problem, and
    the drop app greys these out for "cannot receive".
    """
    from app.delivery.targets import FrequencyTarget

    return FrequencyTarget().missing_credentials_reason(campaign) is None


# ---------------------------------------------------------------------------
# Registering a push
# ---------------------------------------------------------------------------


class PreparedAudio:
    def __init__(self, final_key: str, size: int):
        self.final_key = final_key
        self.size = size


def prepare_pushed_audio(campaign: Campaign, upload_key: str, filename: str) -> PreparedAudio:
    """Fetch the uploaded object, validate it, and make sure MP3 is what gets delivered.

    Raises audio.PushRejected when the file itself is wrong (HTTP 422) and
    botocore ClientError when the object is missing.
    """
    raw = s3.download(upload_key)
    probed = audio.probe(raw, filename)
    expected = frequency_token.creative_duration(campaign.advertiser.frequency_token)
    audio.check_duration(probed, expected)
    if probed.is_mp3:
        return PreparedAudio(upload_key, len(raw))
    return PreparedAudio(_store_transcoded(upload_key, audio.transcode_to_mp3(raw, filename)), len(raw))


def _store_transcoded(upload_key: str, mp3_bytes: bytes) -> str:
    mp3_key = upload_key.rsplit(".", 1)[0] + MP3_SUFFIX
    s3.upload(mp3_key, mp3_bytes)
    return mp3_key


def register_pushed_run(campaign: Campaign, prepared: PreparedAudio, content_hash: str, filename: str) -> AdRun:
    """Create the pending run, or return the existing one if a retry raced us."""
    run = AdRun(
        campaign_id=campaign.id,
        triggered_by=TRIGGER_WATCHER,
        status=STATUS_PENDING,
        source_filename=filename,
        source_content_hash=content_hash,
        source_bytes=prepared.size,
        final_ad_s3_key=prepared.final_key,
    )
    db.session.add(run)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return find_run(campaign, content_hash)
    return run


def requeue_failed_run(run: AdRun) -> None:
    """A re-push of bytes whose run failed is the user asking for another attempt."""
    if run.status != STATUS_FAILED:
        return
    run.status = STATUS_PENDING
    run.error_message = None
    run.completed_at = None
    # The failed attempt stays on the record — the retry appends a new one.
    db.session.commit()
    logger.info("Pushed run #%d re-queued for delivery", run.id)
