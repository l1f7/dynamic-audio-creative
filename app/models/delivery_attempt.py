"""DeliveryAttempt — one record of one ad server being handed one run's audio.

Delivery used to live in seven columns on AdRun, split by target: delivered_at
/ delivery_error / delivery_reference / vast_response for Frequency, and a
parallel dv360_* set beside them. That shape had two costs. Adding a third ad
server meant three more columns and another hand-wired branch at every call
site, and a redelivery overwrote the previous result, so what happened before
was simply lost.

One row per target per attempt instead. AdRun derives its delivery state from
these rows (see AdRun.delivery_state), and the old column names survive there
as read-only properties so serialisers and templates did not have to change.
"""

from datetime import datetime, timezone

from app.extensions import db

TARGET_FREQUENCY = "frequency"
TARGET_DV360 = "dv360"
DELIVERY_TARGETS = (TARGET_FREQUENCY, TARGET_DV360)


class DeliveryAttempt(db.Model):
    __tablename__ = "delivery_attempts"

    id = db.Column(db.Integer, primary_key=True)
    ad_run_id = db.Column(
        db.Integer, db.ForeignKey("ad_runs.id"), nullable=False, index=True
    )

    # Which ad server. Not an enum: a new target should need no migration.
    target = db.Column(db.String(50), nullable=False)
    succeeded = db.Column(db.Boolean, nullable=False)

    # What the ad server gave back on success — VAST XML from Frequency, a
    # creative resource name from DV360. Text because VAST is a whole document.
    reference = db.Column(db.Text, nullable=True)

    # Why it failed, verbatim, for the admin UI and the drop app.
    error = db.Column(db.Text, nullable=True)

    attempted_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    ad_run = db.relationship("AdRun", back_populates="delivery_attempts")

    def __repr__(self):
        outcome = "ok" if self.succeeded else "failed"
        return f"<DeliveryAttempt run={self.ad_run_id} {self.target} {outcome}>"
