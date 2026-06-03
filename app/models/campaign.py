"""Campaign model — one ad configuration for an advertiser."""

from app.extensions import db


# Preset voices available in the dropdown
PRESET_VOICES = {
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Eric": "cjVigY5qzO86Huf0OWal",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "James": "ZQe5CZNOzWyzPSCn5a3c",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Will": "bIHbv24MWmeRgasZH58o",
    "Tyler Cruz": "SA7eD52NRr8WAehitVt1",
}

# Common feed types shown as suggestions — but any value is accepted
FEED_TYPE_SUGGESTIONS = ["weather", "concerts", "events", "news", "sports", "custom"]


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    advertiser_id = db.Column(
        db.Integer, db.ForeignKey("advertisers.id"), nullable=False
    )
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Feed configuration
    feed_type = db.Column(db.String(50), nullable=False)
    feed_url = db.Column(db.String(1000), nullable=True)
    feed_config = db.Column(db.JSON, nullable=True)

    # Target market
    target_city = db.Column(db.String(200), nullable=True)

    # Ad copy — campaign-specific (same advertiser may have different CTAs)
    cta = db.Column(db.String(500), nullable=True)
    seasonal_hook = db.Column(db.String(500), nullable=True)

    # Voice configuration
    voice_preset = db.Column(db.String(100), nullable=True)
    voice_custom_id = db.Column(db.String(100), nullable=True)

    # Music bed (S3 key)
    music_bed_s3_key = db.Column(db.String(500), nullable=True)
    music_bed_filename = db.Column(db.String(200), nullable=True)

    # Mix settings
    intro_seconds = db.Column(db.Float, default=2.0)
    outro_seconds = db.Column(db.Float, default=2.0)
    duck_volume = db.Column(db.Float, default=0.2)
    duck_fade = db.Column(db.Float, default=0.5)

    # Script settings
    prompt_template = db.Column(db.Text, nullable=True)
    target_seconds = db.Column(db.Integer, default=30)
    target_words = db.Column(db.Integer, default=75)
    ad_tags = db.Column(db.JSON, nullable=True)  # list of exact outro/tag strings

    # Schedule
    cron_schedule = db.Column(db.String(100), nullable=True)

    # Delivery configuration
    delivery_enabled = db.Column(db.Boolean, default=False)
    delivery_config = db.Column(db.JSON, nullable=True)
    frequency_app_id = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    # Relationships
    advertiser = db.relationship("Advertiser", back_populates="campaigns")
    pronunciation_entries = db.relationship(
        "PronunciationEntry",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    ad_runs = db.relationship(
        "AdRun",
        back_populates="campaign",
        lazy="dynamic",
        order_by="AdRun.created_at.desc()",
    )

    @property
    def effective_voice_id(self):
        """Return the ElevenLabs voice ID to use.

        Custom ID takes precedence over preset selection.
        """
        if self.voice_custom_id:
            return self.voice_custom_id
        if self.voice_preset:
            return PRESET_VOICES.get(self.voice_preset)
        return PRESET_VOICES.get("Brian")  # default

    @property
    def effective_voice_name(self):
        """Return a display name for the selected voice."""
        if self.voice_custom_id:
            return f"Custom ({self.voice_custom_id[:12]}...)"
        return self.voice_preset or "Brian"

    def __repr__(self):
        return f"<Campaign {self.id}: {self.name}>"
