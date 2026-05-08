"""Advertiser model — the business entity paying for ads."""

from app.extensions import db


class Advertiser(db.Model):
    __tablename__ = "advertisers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tagline = db.Column(db.String(500), nullable=True)
    cta = db.Column(db.String(500), nullable=True)
    seasonal_hook = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    campaigns = db.relationship(
        "Campaign", back_populates="advertiser", lazy="dynamic"
    )

    def __repr__(self):
        return f"<Advertiser {self.id}: {self.name}>"
