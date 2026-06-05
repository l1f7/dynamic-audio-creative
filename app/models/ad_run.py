"""AdRun model — tracks each ad generation attempt."""

from app.extensions import db


RUN_STATUSES = [
    "pending",
    "fetching_data",
    "generating_script",
    "generating_voiceover",
    "mixing",
    "uploading",
    "delivering",
    "complete",
    "failed",
]


class AdRun(db.Model):
    __tablename__ = "ad_runs"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaigns.id"), nullable=False
    )

    # Status tracking
    status = db.Column(db.String(30), nullable=False, default="pending")
    triggered_by = db.Column(db.String(20), nullable=False)  # manual, cron, api

    # Pipeline outputs (S3 keys)
    voiceover_s3_key = db.Column(db.String(500), nullable=True)
    final_ad_s3_key = db.Column(db.String(500), nullable=True)

    # Script text (kept for review)
    script_text = db.Column(db.Text, nullable=True)

    # Feed data snapshot (for debugging)
    feed_data_snapshot = db.Column(db.JSON, nullable=True)

    # Error info
    error_message = db.Column(db.Text, nullable=True)

    # Frequency delivery
    delivered_at = db.Column(db.DateTime, nullable=True)
    delivery_reference = db.Column(db.String(500), nullable=True)
    delivery_error = db.Column(db.Text, nullable=True)
    vast_response = db.Column(db.Text, nullable=True)

    # DV360 delivery
    dv360_delivered_at = db.Column(db.DateTime, nullable=True)
    dv360_creative_name = db.Column(db.String(500), nullable=True)
    dv360_delivery_error = db.Column(db.Text, nullable=True)

    # Job tracking
    job_id = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    campaign = db.relationship("Campaign", back_populates="ad_runs")

    @property
    def is_terminal(self):
        """Whether this run has reached a final state."""
        return self.status in ("complete", "failed")

    @property
    def status_label(self):
        """Human-readable status for the UI."""
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
