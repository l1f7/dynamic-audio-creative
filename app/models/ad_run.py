"""AdRun model — tracks each ad generation attempt."""

from app.extensions import db
from app.models.delivery_attempt import (
    DELIVERY_TARGETS,
    TARGET_DV360,
    TARGET_FREQUENCY,
    DeliveryAttempt,
)


TRIGGER_MANUAL = "manual"
TRIGGER_CRON = "cron"
TRIGGER_API = "api"
TRIGGER_WATCHER = "watcher"  # file pushed from a desktop watch folder
TRIGGERED_BY_VALUES = [TRIGGER_MANUAL, TRIGGER_CRON, TRIGGER_API, TRIGGER_WATCHER]

# The run lifecycle. These names are the single source of truth — app.pipeline
# .runner, app.jobs.scheduler and app.push.service all import them rather than
# retyping the literals, which is how the vocabulary drifted three ways before.
STATUS_PENDING = "pending"
STATUS_FETCHING_DATA = "fetching_data"
STATUS_GENERATING_SCRIPT = "generating_script"
STATUS_GENERATING_VOICEOVER = "generating_voiceover"
STATUS_MIXING = "mixing"
STATUS_UPLOADING = "uploading"
STATUS_DELIVERING = "delivering"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

RUN_STATUSES = [
    STATUS_PENDING,
    STATUS_FETCHING_DATA,
    STATUS_GENERATING_SCRIPT,
    STATUS_GENERATING_VOICEOVER,
    STATUS_MIXING,
    STATUS_UPLOADING,
    STATUS_DELIVERING,
    STATUS_COMPLETE,
    STATUS_FAILED,
]

# Terminal states. The scheduler treats anything else as "still running" and
# will not start another run for that campaign.
TERMINAL_STATUSES = (STATUS_COMPLETE, STATUS_FAILED)

# How far each ad server got. Derived from the run's own per-target columns,
# never stored — see AdRun.delivery_state.
DELIVERY_NOT_ATTEMPTED = "not_attempted"
DELIVERY_DELIVERED = "delivered"
DELIVERY_PARTIAL = "partial"
DELIVERY_FAILED = "failed"



# A pushed file skips generation, so "Pending" means waiting for the delivery tick
PUSHED_STATUS_LABELS = {
    "pending": "Waiting for delivery...",
    "uploading": "Receiving file...",
    "delivering": "Delivering to ad server...",
}


class AdRun(db.Model):
    __tablename__ = "ad_runs"
    # Server-side idempotency for pushed files: the daemon retries freely and a
    # repeated push of the same bytes must land on the same run.
    __table_args__ = (
        db.UniqueConstraint("campaign_id", "source_content_hash", name="uq_ad_runs_campaign_content_hash"),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaigns.id"), nullable=False
    )

    # Status tracking
    status = db.Column(db.String(30), nullable=False, default="pending")
    triggered_by = db.Column(db.String(20), nullable=False)  # see TRIGGERED_BY_VALUES

    # Pipeline outputs (S3 keys)
    voiceover_s3_key = db.Column(db.String(500), nullable=True)
    final_ad_s3_key = db.Column(db.String(500), nullable=True)

    # Script text (kept for review)
    script_text = db.Column(db.Text, nullable=True)
    # Where the script came from: "feed", "fallback", or "manual_override"
    script_source = db.Column(db.String(20), nullable=True)

    # Time-stretch applied during mixing to fit the campaign target duration.
    # Factor is the FFmpeg atempo applied (>1.0 = sped up / compressed).
    # Null means no stretching ran (e.g. voiceover already within target).
    stretch_factor = db.Column(db.Float, nullable=True)

    # Pushed files: original name, blake3 hex of the bytes, and their size
    source_filename = db.Column(db.String(500), nullable=True)
    source_content_hash = db.Column(db.String(64), nullable=True, index=True)
    source_bytes = db.Column(db.BigInteger, nullable=True)

    # Feed data snapshot (for debugging)
    feed_data_snapshot = db.Column(db.JSON, nullable=True)

    # Error info
    error_message = db.Column(db.Text, nullable=True)

    # Delivery lives in delivery_attempts — one row per ad server per attempt.
    # The old per-target columns survive below as read-only properties.

    # Job tracking
    job_id = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    campaign = db.relationship("Campaign", back_populates="ad_runs")
    delivery_attempts = db.relationship(
        "DeliveryAttempt",
        back_populates="ad_run",
        cascade="all, delete-orphan",
        order_by="DeliveryAttempt.attempted_at",
    )

    # Flag the audio as heavily retimed once it's been sped up by more than this.
    HEAVY_STRETCH_THRESHOLD = 1.10  # 10%

    @property
    def is_pushed(self):
        return self.triggered_by == TRIGGER_WATCHER

    @property
    def is_terminal(self):
        """Whether this run has reached a final state."""
        return self.status in TERMINAL_STATUSES

    def latest_attempt(self, target):
        """The most recent attempt against one ad server, or None."""
        for attempt in reversed(self.delivery_attempts):
            if attempt.target == target:
                return attempt
        return None

    def record_delivery(self, target, succeeded, reference=None, error=None, detail=None):
        """Append what one ad server (or one ad unit within it) did with this run.

        The only way delivery results get written. Every caller goes through
        app.delivery.deliver_run rather than touching this directly.
        """
        attempt = DeliveryAttempt(
            target=target, succeeded=succeeded, reference=reference, error=error, detail=detail
        )
        self.delivery_attempts.append(attempt)
        return attempt

    @property
    def attempted_targets(self):
        """Each (ad server, ad unit) this run tried, with whether it stuck.

        Keyed on the latest attempt per target+detail, so a redelivery that
        succeeds after an earlier failure reads as delivered — while both rows
        survive, and a target with several ad units (Frequency's tags) reports
        each one rather than only its most recent attempt overall.
        """
        latest = {}
        for attempt in self.delivery_attempts:
            latest[(attempt.target, attempt.detail)] = attempt
        return [(target, a.succeeded) for (target, _detail), a in latest.items()]

    @property
    def delivery_state(self):
        """How far this run got with the ad servers.

        `status` answers "did we make the audio". This answers "did anyone
        receive it" — the two used to be conflated, so a run that reached no
        ad server at all still showed a green Complete.
        """
        attempts = self.attempted_targets
        if not attempts:
            return DELIVERY_NOT_ATTEMPTED
        succeeded = [ok for _, ok in attempts]
        if all(succeeded):
            return DELIVERY_DELIVERED
        if any(succeeded):
            return DELIVERY_PARTIAL
        return DELIVERY_FAILED

    @property
    def delivery_errors(self):
        """Every current ad-server error on this run, as 'target: message'."""
        errors = []
        for target, _ in self.attempted_targets:
            attempt = self.latest_attempt(target)
            if attempt and not attempt.succeeded and attempt.error:
                errors.append(f"{target}: {attempt.error}")
        return errors

    # ---- Backwards-compatible views of the old per-target columns ----
    # Read-only on purpose: writes go through record_delivery so the attempt
    # history stays the single source of truth.

    def _delivered_at_for(self, target):
        attempt = self.latest_attempt(target)
        return attempt.attempted_at if attempt and attempt.succeeded else None

    def _error_for(self, target):
        attempt = self.latest_attempt(target)
        return attempt.error if attempt and not attempt.succeeded else None

    def _reference_for(self, target):
        attempt = self.latest_attempt(target)
        return attempt.reference if attempt and attempt.succeeded else None

    @property
    def delivered_at(self):
        return self._delivered_at_for(TARGET_FREQUENCY)

    @property
    def delivery_error(self):
        return self._error_for(TARGET_FREQUENCY)

    @property
    def vast_response(self):
        return self._reference_for(TARGET_FREQUENCY)

    @property
    def delivery_reference(self):
        """Which ad server holds this run's live creative, if any."""
        return TARGET_FREQUENCY if self.delivered_at else None

    @property
    def dv360_delivered_at(self):
        return self._delivered_at_for(TARGET_DV360)

    @property
    def dv360_delivery_error(self):
        return self._error_for(TARGET_DV360)

    @property
    def dv360_creative_name(self):
        return self._reference_for(TARGET_DV360)

    @property
    def delivery_label(self):
        """Human-readable delivery outcome for the UI."""
        return {
            DELIVERY_NOT_ATTEMPTED: "Not delivered",
            DELIVERY_DELIVERED: "Delivered",
            DELIVERY_PARTIAL: "Partially delivered",
            DELIVERY_FAILED: "Delivery failed",
        }[self.delivery_state]

    @property
    def stretch_pct(self):
        """Percentage the voiceover was sped up, or None if not stretched.

        e.g. a stretch_factor of 1.15 → 15 (15% faster).
        """
        if not self.stretch_factor:
            return None
        return round((self.stretch_factor - 1) * 100)

    @property
    def is_heavily_stretched(self):
        """Whether the audio was time-stretched beyond the 10% threshold."""
        return bool(self.stretch_factor) and self.stretch_factor > self.HEAVY_STRETCH_THRESHOLD

    @property
    def status_label(self):
        """Human-readable status for the UI."""
        if self.is_pushed and self.status in PUSHED_STATUS_LABELS:
            return PUSHED_STATUS_LABELS[self.status]
        labels = {
            "pending": "Pending",
            "fetching_data": "Fetching data...",
            "generating_script": "Generating script...",
            "generating_voiceover": "Generating voiceover...",
            "mixing": "Mixing audio...",
            "uploading": "Uploading...",
            "delivering": "Delivering to ad server...",
            "complete": "Complete",
            "failed": "Failed",
        }
        return labels.get(self.status, self.status)

    def __repr__(self):
        return f"<AdRun {self.id}: {self.status}>"
