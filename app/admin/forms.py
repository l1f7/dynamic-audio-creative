"""WTForms for the admin UI."""

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Optional, NumberRange

from app.models.campaign import FEED_TYPES, PRESET_VOICES


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class AdvertiserForm(FlaskForm):
    name = StringField("Advertiser Name", validators=[DataRequired()])
    tagline = StringField("Tagline", validators=[Optional()])
    cta = StringField("Call to Action", validators=[Optional()])
    seasonal_hook = StringField("Seasonal Hook", validators=[Optional()])
    is_active = BooleanField("Active", default=True)


class CampaignForm(FlaskForm):
    name = StringField("Campaign Name", validators=[DataRequired()])
    advertiser_id = SelectField("Advertiser", coerce=int, validators=[DataRequired()])
    is_active = BooleanField("Active", default=True)

    # Feed
    feed_type = SelectField(
        "Feed Type",
        choices=FEED_TYPES,
        validators=[DataRequired()],
    )
    feed_url = StringField("Feed URL", validators=[Optional()])
    target_city = StringField("Target City", validators=[Optional()])

    # Voice
    voice_preset = SelectField(
        "Voice (Preset)",
        choices=[("", "-- Select --")] + [(k, k) for k in PRESET_VOICES],
        validators=[Optional()],
    )
    voice_custom_id = StringField(
        "Custom Voice ID (overrides preset)", validators=[Optional()]
    )

    # Mix settings
    intro_seconds = FloatField(
        "Music Intro (seconds)",
        default=2.0,
        validators=[NumberRange(min=0, max=10)],
    )
    outro_seconds = FloatField(
        "Music Outro (seconds)",
        default=2.0,
        validators=[NumberRange(min=0, max=10)],
    )
    duck_volume = FloatField(
        "Duck Volume (0.0-1.0)",
        default=0.2,
        validators=[NumberRange(min=0, max=1)],
    )
    duck_fade = FloatField(
        "Duck Fade (seconds)",
        default=0.5,
        validators=[NumberRange(min=0, max=5)],
    )

    # Script
    prompt_template = TextAreaField("Prompt Template (leave blank for default)", validators=[Optional()])
    target_seconds = IntegerField("Target Length (seconds)", default=30)
    target_words = IntegerField("Target Words", default=75)

    # Schedule
    cron_schedule = StringField(
        "Cron Schedule (leave blank for manual only)", validators=[Optional()]
    )
