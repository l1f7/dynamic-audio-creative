"""Register pushed files as runs. Delivery happens on the scheduler tick."""

import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.delivery import frequency_token
from app.extensions import db
from app.models import AdRun, Campaign
from app.models.ad_run import TRIGGER_WATCHER
from app.push import audio
from app.storage import s3

logger = logging.getLogger(__name__)

UPLOAD_PREFIX = "pushed"
UPLOAD_URL_TTL_SECONDS = 30 * 60  # matches the daemon's allowance for the PUT
DEFAULT_SUFFIX = ".bin"
MP3_SUFFIX = ".mp3"

STATUS_PENDING = "pending"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


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
    if run and run.delivered_at is not None and not run.delivery_error:
        return run
    return None


def active_run_id(campaign: Campaign) -> int | None:
    """The run whose creative DAC believes is live.

    Frequency has no "which creative is live" endpoint, so this is DAC's own
    record: the most recent run delivered without error.
    """
    run = (
        campaign.ad_runs
        .filter(AdRun.delivered_at.isnot(None), AdRun.delivery_error.is_(None))
        .order_by(AdRun.delivered_at.desc())
        .first()
    )
    return run.id if run else None


def is_deliverable(campaign: Campaign) -> bool:
    advertiser = campaign.advertiser
    return bool(
        campaign.frequency_app_id
        and advertiser.frequency_client
        and advertiser.frequency_token
    )


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
    run.delivery_error = None
    run.error_message = None
    run.completed_at = None
    db.session.commit()
    logger.info("Pushed run #%d re-queued for delivery", run.id)
