"""Advertiser model — the business entity paying for ads."""

from app.extensions import db


class Advertiser(db.Model):
    __tablename__ = "advertisers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)  # who they are, what they do
    tagline = db.Column(db.String(500), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Frequency ad server credentials
    frequency_client = db.Column(db.String(100), nullable=True)
    frequency_token = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    campaigns = db.relationship(
        "Campaign", back_populates="advertiser", lazy="dynamic"
    )

    def __repr__(self):
        return f"<Advertiser {self.id}: {self.name}>"
