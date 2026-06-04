"""WTForms for the admin UI."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, Regexp, ValidationError

from app.models import AdminUser
from app.models.campaign import PRESET_VOICES

PASSWORD_MIN_LENGTH = 12
EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _normalize_email(value):
    return AdminUser.normalize_email(value)


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class AdvertiserForm(FlaskForm):
    name = StringField("Advertiser Name", validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Optional()])
    tagline = StringField("Tagline", validators=[Optional()])
    website = StringField("Website", validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    frequency_client = StringField("Frequency Client Name", validators=[Optional()])
    frequency_token = StringField("Frequency Token", validators=[Optional()])


class CampaignForm(FlaskForm):
    name = StringField("Campaign Name", validators=[DataRequired()])
    advertiser_id = SelectField("Advertiser", coerce=int, validators=[DataRequired()])
    is_active = BooleanField("Active", default=True)

    # Feed
    feed_type = StringField("Feed Type", validators=[DataRequired()])
    feed_url = StringField("Feed URL", validators=[Optional()])
    target_city = StringField("Target City", validators=[Optional()])

    # Ad copy
    cta = StringField("Call to Action", validators=[Optional()])
    seasonal_hook = StringField("Seasonal Hook", validators=[Optional()])

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

    # Music bed
    music_bed_file = FileField(
        "Music Bed",
        validators=[
            FileAllowed(["mp3", "wav", "m4a"], "Audio files only (MP3, WAV, M4A)."),
        ],
    )
    remove_music_bed = BooleanField("Remove music bed")

    # Script
    prompt_template = TextAreaField("Prompt Template (leave blank for default)", validators=[Optional()])
    fallback_script = TextAreaField("Fallback Script (used when feed has no data or errors)", validators=[Optional()])
    target_seconds = IntegerField("Target Length (seconds)", default=30)
    target_words = IntegerField("Target Words", default=75)

    # Schedule
    cron_schedule = StringField(
        "Cron Schedule (leave blank for manual only)", validators=[Optional()]
    )

    # Delivery
    delivery_enabled = BooleanField("Enable Frequency Delivery", default=False)
    frequency_app_id = StringField("Frequency App ID", validators=[Optional()])


class AdminUserCreateForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Regexp(EMAIL_REGEX, message="Enter a valid email address.")],
    )
    full_name = StringField("Full Name", validators=[Optional()])
    temporary_password = PasswordField(
        "Temporary Password",
        validators=[DataRequired(), Length(min=PASSWORD_MIN_LENGTH)],
    )
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Create User")

    def validate_email(self, field):
        normalized_email = _normalize_email(field.data)
        if AdminUser.query.filter_by(email=normalized_email).first():
            raise ValidationError("A user with that email already exists.")


class AdminUserEditForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Regexp(EMAIL_REGEX, message="Enter a valid email address.")],
    )
    full_name = StringField("Full Name", validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Changes")

    def __init__(self, original_user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_user = original_user

    def validate_email(self, field):
        normalized_email = _normalize_email(field.data)
        query = AdminUser.query.filter_by(email=normalized_email)
        if self.original_user is not None:
            query = query.filter(AdminUser.id != self.original_user.id)
        if query.first():
            raise ValidationError("A user with that email already exists.")


class AdminUserResetPasswordForm(FlaskForm):
    temporary_password = PasswordField(
        "Temporary Password",
        validators=[DataRequired(), Length(min=PASSWORD_MIN_LENGTH)],
    )
    submit = SubmitField("Reset Password")


class ChangeOwnPasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=PASSWORD_MIN_LENGTH),
            EqualTo("confirm_new_password", message="Passwords must match."),
        ],
    )
    confirm_new_password = PasswordField(
        "Confirm New Password", validators=[DataRequired()]
    )
    submit = SubmitField("Change Password")


class SimpleActionForm(FlaskForm):
    submit = SubmitField("Submit")
