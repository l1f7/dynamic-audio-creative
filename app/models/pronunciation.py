"""PronunciationEntry model — TTS pronunciation overrides per campaign."""

from app.extensions import db


class PronunciationEntry(db.Model):
    __tablename__ = "pronunciation_entries"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaigns.id"), nullable=False
    )
    written_form = db.Column(db.String(200), nullable=False)
    spoken_form = db.Column(db.String(200), nullable=False)

    campaign = db.relationship("Campaign", back_populates="pronunciation_entries")

    def __repr__(self):
        return f"<Pronunciation '{self.written_form}' -> '{self.spoken_form}'>"
