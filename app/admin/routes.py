"""Admin blueprint routes — CRUD for advertisers and campaigns."""

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename
from flask_login import current_user, login_required, login_user, logout_user

from app.admin import admin_bp
from app.admin.auth import (
    authenticate_bootstrap_user,
    authenticate_database_user,
)
from app.admin.forms import (
    AdminUserCreateForm,
    AdminUserEditForm,
    AdminUserResetPasswordForm,
    AdvertiserForm,
    CampaignForm,
    ChangeOwnPasswordForm,
    LoginForm,
    SimpleActionForm,
)
from app.extensions import db
from app.models import AdRun, AdminUser, Advertiser, Campaign, PronunciationEntry


PASSWORD_CHANGE_ENDPOINT = "admin.account_password"
MUST_CHANGE_ALLOWED_ENDPOINTS = {
    "admin.account_password",
    "admin.logout",
}
SCHEMA_TABLES = {
    "ad_runs",
    "admin_users",
    "advertisers",
    "campaigns",
    "pronunciation_entries",
}

logger = logging.getLogger(__name__)


@admin_bp.before_request
def ensure_database_schema():
    try:
        existing_tables = set(inspect(db.engine).get_table_names())
        missing_tables = sorted(SCHEMA_TABLES - existing_tables)
        if missing_tables:
            logger.warning(
                "Missing database tables detected: %s. Creating tables from models.",
                ", ".join(missing_tables),
            )
            db.create_all()
    except (OperationalError, ProgrammingError):
        logger.exception("Database schema check failed for admin request")
        db.session.rollback()

    return None


@admin_bp.before_request
def enforce_password_change():
    if not current_user.is_authenticated or getattr(current_user, "is_bootstrap", False):
        return None

    if request.endpoint in MUST_CHANGE_ALLOWED_ENDPOINTS:
        return None

    if getattr(current_user, "must_change_password", False):
        flash("Change your password before continuing.", "warning")
        return redirect(url_for(PASSWORD_CHANGE_ENDPOINT))

    return None


# ---- Auth ----

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, "must_change_password", False):
            return redirect(url_for(PASSWORD_CHANGE_ENDPOINT))
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_database_user(form.email.data, form.password.data)
        if user is None:
            user = authenticate_bootstrap_user(form.email.data, form.password.data)

        if user is not None:
            login_user(user)
            if isinstance(user, AdminUser):
                user.last_login_at = datetime.now(timezone.utc)
                db.session.commit()
            next_page = request.args.get("next")
            if isinstance(user, AdminUser) and user.must_change_password:
                return redirect(url_for(PASSWORD_CHANGE_ENDPOINT))
            return redirect(next_page or url_for("admin.dashboard"))
        flash("Invalid credentials.", "danger")

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@admin_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def account_password():
    if getattr(current_user, "is_bootstrap", False):
        flash("Bootstrap admin password is managed via environment variables.", "info")
        return redirect(url_for("admin.dashboard"))

    form = ChangeOwnPasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        else:
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("admin.dashboard"))

    return render_template("admin/account_password.html", form=form)


# ---- Dashboard ----

@admin_bp.route("/")
@login_required
def dashboard():
    advertisers = Advertiser.query.filter_by(is_active=True).all()
    campaigns = Campaign.query.filter_by(is_active=True).all()
    recent_runs = AdRun.query.order_by(AdRun.created_at.desc()).limit(10).all()
    return render_template(
        "admin/dashboard.html",
        advertisers=advertisers,
        campaigns=campaigns,
        recent_runs=recent_runs,
    )


# ---- Admin Users ----

@admin_bp.route("/users")
@login_required
def user_list():
    users = AdminUser.query.order_by(AdminUser.email).all()
    action_form = SimpleActionForm()
    return render_template("admin/user_list.html", users=users, action_form=action_form)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
def user_new():
    form = AdminUserCreateForm()
    if form.validate_on_submit():
        user = AdminUser(
            email=form.email.data,
            full_name=form.full_name.data or None,
            is_active=form.is_active.data,
            must_change_password=True,
            created_by_user_id=_current_db_admin_id(),
        )
        user.set_password(form.temporary_password.data)
        db.session.add(user)
        db.session.commit()
        flash(f"User '{user.email}' created.", "success")
        return redirect(url_for("admin.user_list"))

    return render_template(
        "admin/user_form.html",
        form=form,
        editing=False,
        user=None,
        reset_form=None,
    )


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def user_edit(user_id):
    user = AdminUser.query.get_or_404(user_id)
    form = AdminUserEditForm(original_user=user, obj=user)
    reset_form = AdminUserResetPasswordForm()

    if form.validate_on_submit():
        if user.is_active and not form.is_active.data and _is_last_active_db_user(user):
            flash("You cannot deactivate the last active admin user.", "danger")
        else:
            user.email = form.email.data
            user.full_name = form.full_name.data or None
            user.is_active = form.is_active.data
            db.session.commit()
            flash(f"User '{user.email}' updated.", "success")
            if _is_current_db_user(user) and not user.is_active:
                logout_user()
                flash("Your account has been deactivated.", "warning")
                return redirect(url_for("admin.login"))
            return redirect(url_for("admin.user_edit", user_id=user.id))

    return render_template(
        "admin/user_form.html",
        form=form,
        editing=True,
        user=user,
        reset_form=reset_form,
    )


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
def user_reset_password(user_id):
    user = AdminUser.query.get_or_404(user_id)
    form = AdminUserResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.temporary_password.data)
        user.must_change_password = True
        db.session.commit()
        flash(f"Password reset for '{user.email}'.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("admin.user_edit", user_id=user.id) + "#password-reset")


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
def user_toggle_active(user_id):
    user = AdminUser.query.get_or_404(user_id)
    form = SimpleActionForm()
    if not form.validate_on_submit():
        abort(400)

    if user.is_active and _is_last_active_db_user(user):
        flash("You cannot deactivate the last active admin user.", "danger")
        return redirect(url_for("admin.user_list"))

    user.is_active = not user.is_active
    db.session.commit()

    if not user.is_active and _is_current_db_user(user):
        logout_user()
        flash("Your account has been deactivated.", "warning")
        return redirect(url_for("admin.login"))

    flash(
        f"User '{user.email}' {'activated' if user.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("admin.user_list"))


# ---- Advertisers ----

@admin_bp.route("/advertisers")
@login_required
def advertiser_list():
    advertisers = Advertiser.query.order_by(Advertiser.name).all()
    return render_template("admin/advertiser_list.html", advertisers=advertisers)


@admin_bp.route("/advertisers/new", methods=["GET", "POST"])
@login_required
def advertiser_new():
    form = AdvertiserForm()
    if form.validate_on_submit():
        adv = Advertiser(
            name=form.name.data,
            description=form.description.data or None,
            tagline=form.tagline.data or None,
            website=form.website.data or None,
            is_active=form.is_active.data,
            frequency_client=form.frequency_client.data or None,
            frequency_token=form.frequency_token.data or None,
            dv360_advertiser_id=form.dv360_advertiser_id.data or None,
            dv360_service_account_json=_minify_json(form.dv360_service_account_json.data),
        )
        db.session.add(adv)
        db.session.commit()
        flash(f"Advertiser '{adv.name}' created.", "success")
        return redirect(url_for("admin.advertiser_list"))

    return render_template("admin/advertiser_form.html", form=form, editing=False)


@admin_bp.route("/advertisers/<int:adv_id>/edit", methods=["GET", "POST"])
@login_required
def advertiser_edit(adv_id):
    adv = Advertiser.query.get_or_404(adv_id)
    form = AdvertiserForm(obj=adv)

    if form.validate_on_submit():
        form.populate_obj(adv)
        adv.dv360_service_account_json = _minify_json(adv.dv360_service_account_json)
        db.session.commit()
        flash(f"Advertiser '{adv.name}' updated.", "success")
        return redirect(url_for("admin.advertiser_list"))

    return render_template("admin/advertiser_form.html", form=form, editing=True, advertiser=adv)


# ---- Campaigns ----

@admin_bp.route("/campaigns")
@login_required
def campaign_list():
    campaigns = Campaign.query.order_by(Campaign.name).all()
    return render_template("admin/campaign_list.html", campaigns=campaigns)


@admin_bp.route("/campaigns/new", methods=["GET", "POST"])
@login_required
def campaign_new():
    form = CampaignForm()
    form.advertiser_id.choices = [
        (a.id, a.name) for a in Advertiser.query.order_by(Advertiser.name).all()
    ]

    if form.validate_on_submit():
        campaign = Campaign(
            name=form.name.data,
            advertiser_id=form.advertiser_id.data,
            is_active=form.is_active.data,
            feed_type=form.feed_type.data,
            feed_url=form.feed_url.data or None,
            target_city=form.target_city.data or None,
            cta=form.cta.data or None,
            seasonal_hook=form.seasonal_hook.data or None,
            voice_preset=form.voice_preset.data or None,
            voice_custom_id=form.voice_custom_id.data.strip() or None,
            intro_seconds=form.intro_seconds.data,
            outro_seconds=form.outro_seconds.data,
            duck_volume=form.duck_volume.data,
            duck_fade=form.duck_fade.data,
            prompt_template=form.prompt_template.data or None,
            fallback_script=form.fallback_script.data or None,
            target_seconds=form.target_seconds.data,
            target_words=form.target_words.data,
            cron_schedule=form.cron_schedule.data or None,
            frequency_app_id=form.frequency_app_id.data or None,
            dv360_enabled=form.dv360_enabled.data,
            dv360_line_item_id=form.dv360_line_item_id.data or None,
        )
        db.session.add(campaign)
        db.session.commit()

        # Upload music bed if provided
        _handle_music_bed_upload(campaign, form)

        # Save pronunciation entries from form
        _save_pronunciation_entries(campaign, request.form)

        # Save ad tags from form
        _save_ad_tags(campaign, request.form)

        flash(f"Campaign '{campaign.name}' created.", "success")
        return redirect(url_for("admin.campaign_detail", campaign_id=campaign.id))

    return render_template(
        "admin/campaign_form.html",
        form=form,
        editing=False,
        feed_type_suggestions=_get_feed_type_suggestions(),
    )


@admin_bp.route("/campaigns/<int:campaign_id>")
@login_required
def campaign_detail(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    runs = campaign.ad_runs.limit(20).all()
    return render_template(
        "admin/campaign_detail.html",
        campaign=campaign,
        runs=runs,
    )


@admin_bp.route("/campaigns/<int:campaign_id>/generate", methods=["POST"])
@login_required
def campaign_generate(campaign_id):
    """Trigger ad generation for a campaign (runs synchronously for now)."""
    campaign = Campaign.query.get_or_404(campaign_id)

    from app.pipeline.runner import run_pipeline
    ad_run = run_pipeline(campaign.id, triggered_by="manual")

    if ad_run.status == "complete":
        flash("Ad generated successfully!", "success")
    else:
        flash(f"Generation failed: {ad_run.error_message}", "danger")

    return redirect(url_for("admin.campaign_detail", campaign_id=campaign.id))


@admin_bp.route("/runs/<int:run_id>")
@login_required
def run_detail(run_id):
    """Show details of an ad run — script, status, audio player."""
    ad_run = AdRun.query.get_or_404(run_id)
    return render_template("admin/run_detail.html", run=ad_run)


@admin_bp.route("/runs/<int:run_id>/delete", methods=["POST"])
@login_required
def run_delete(run_id):
    """Delete an ad run and its associated audio files."""
    ad_run = AdRun.query.get_or_404(run_id)
    campaign_id = ad_run.campaign_id

    # Clean up audio files
    s3_keys = [ad_run.voiceover_s3_key, ad_run.final_ad_s3_key]
    for key in s3_keys:
        if not key:
            continue
        if os.path.isfile(key):
            # Local dev file
            try:
                os.remove(key)
            except OSError:
                pass
        else:
            # S3
            try:
                from flask import current_app
                if current_app.config.get("S3_ENDPOINT_URL"):
                    from app.storage import s3
                    s3.delete(key)
            except Exception:
                pass  # best-effort cleanup

    db.session.delete(ad_run)
    db.session.commit()
    flash(f"Run #{run_id} deleted.", "info")
    return redirect(url_for("admin.campaign_detail", campaign_id=campaign_id))


@admin_bp.route("/runs/<int:run_id>/redeliver", methods=["POST"])
@login_required
def run_redeliver(run_id):
    """Re-deliver an existing run's audio to Frequency and/or DV360."""
    ad_run = AdRun.query.get_or_404(run_id)

    if not ad_run.final_ad_s3_key:
        flash("No audio available to resubmit.", "danger")
        return redirect(url_for("admin.run_detail", run_id=run_id))

    deliver_frequency = bool(request.form.get("deliver_frequency"))
    deliver_dv360 = bool(request.form.get("deliver_dv360"))

    if not deliver_frequency and not deliver_dv360:
        flash("Select at least one delivery target.", "warning")
        return redirect(url_for("admin.run_detail", run_id=run_id))

    from app.pipeline.runner import redeliver
    redeliver(run_id, deliver_frequency=deliver_frequency, deliver_dv360=deliver_dv360)

    # Refresh to pick up any error fields
    db.session.refresh(ad_run)
    errors = []
    if deliver_frequency and ad_run.delivery_error:
        errors.append(f"Frequency: {ad_run.delivery_error}")
    if deliver_dv360 and ad_run.dv360_delivery_error:
        errors.append(f"DV360: {ad_run.dv360_delivery_error}")

    if errors:
        flash("Resubmit failed: " + "; ".join(errors), "danger")
    else:
        targets = []
        if deliver_frequency:
            targets.append("Frequency")
        if deliver_dv360:
            targets.append("DV360")
        flash(f"Resubmitted to {' and '.join(targets)}.", "success")

    return redirect(url_for("admin.run_detail", run_id=run_id))


@admin_bp.route("/runs/<int:run_id>/regenerate", methods=["POST"])
@login_required
def run_regenerate(run_id):
    """Re-generate voiceover + mix from an edited script."""
    ad_run = AdRun.query.get_or_404(run_id)
    script = request.form.get("script", "").strip()
    if not script:
        flash("Script cannot be empty.", "danger")
        return redirect(url_for("admin.run_detail", run_id=run_id))

    deliver_frequency = bool(request.form.get("deliver_frequency"))
    deliver_dv360 = bool(request.form.get("deliver_dv360"))

    from app.pipeline.runner import rerun_from_script
    new_run = rerun_from_script(run_id, script, deliver_frequency=deliver_frequency, deliver_dv360=deliver_dv360)

    if new_run.status == "complete":
        flash(f"Run #{new_run.id} created.", "success")
    else:
        flash(f"Run #{new_run.id} failed: {new_run.error_message}", "danger")

    return redirect(url_for("admin.run_detail", run_id=new_run.id))


@admin_bp.route("/runs/<int:run_id>/audio")
@login_required
def run_audio(run_id):
    """Serve the final ad MP3 for playback or download."""
    ad_run = AdRun.query.get_or_404(run_id)

    if not ad_run.final_ad_s3_key:
        flash("No audio available for this run.", "warning")
        return redirect(url_for("admin.run_detail", run_id=run_id))

    # Local file (dev) — serve directly
    if os.path.isfile(ad_run.final_ad_s3_key):
        return send_file(
            ad_run.final_ad_s3_key,
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name=f"ad_run_{run_id}.mp3",
        )

    # S3 — redirect to signed URL
    from flask import current_app
    if current_app.config.get("S3_ENDPOINT_URL"):
        from app.storage import s3
        url = s3.generate_signed_url(ad_run.final_ad_s3_key)
        return redirect(url)

    flash("Audio file not found.", "danger")
    return redirect(url_for("admin.run_detail", run_id=run_id))


@admin_bp.route("/runs/<int:run_id>/download")
@login_required
def run_download(run_id):
    """Download the final ad MP3."""
    ad_run = AdRun.query.get_or_404(run_id)

    if not ad_run.final_ad_s3_key:
        flash("No audio available for this run.", "warning")
        return redirect(url_for("admin.run_detail", run_id=run_id))

    if os.path.isfile(ad_run.final_ad_s3_key):
        return send_file(
            ad_run.final_ad_s3_key,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=f"ad_{ad_run.campaign.name}_{run_id}.mp3",
        )

    from flask import current_app
    if current_app.config.get("S3_ENDPOINT_URL"):
        from app.storage import s3
        url = s3.generate_signed_url(ad_run.final_ad_s3_key)
        return redirect(url)

    flash("Audio file not found.", "danger")
    return redirect(url_for("admin.run_detail", run_id=run_id))


@admin_bp.route("/campaigns/<int:campaign_id>/music-bed")
@login_required
def campaign_music_bed(campaign_id):
    """Serve the campaign's music bed for playback."""
    campaign = Campaign.query.get_or_404(campaign_id)

    if campaign.music_bed_s3_key and current_app.config.get("S3_ENDPOINT_URL"):
        from app.storage import s3
        url = s3.generate_signed_url(campaign.music_bed_s3_key)
        return redirect(url)

    local_path = campaign.music_bed_filename
    if local_path and os.path.isfile(local_path):
        return send_file(local_path, mimetype="audio/mpeg")

    flash("No music bed found.", "warning")
    return redirect(url_for("admin.campaign_edit", campaign_id=campaign_id))


@admin_bp.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
@login_required
def campaign_edit(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    form = CampaignForm(obj=campaign)
    form.advertiser_id.choices = [
        (a.id, a.name) for a in Advertiser.query.order_by(Advertiser.name).all()
    ]

    if form.validate_on_submit():
        # Preserve music bed fields — populate_obj would overwrite them
        saved_s3_key = campaign.music_bed_s3_key
        saved_filename = campaign.music_bed_filename

        form.populate_obj(campaign)

        # Restore music bed fields (handled separately via _handle_music_bed_upload)
        campaign.music_bed_s3_key = saved_s3_key
        campaign.music_bed_filename = saved_filename

        # Clear empty strings to None
        if not campaign.feed_url:
            campaign.feed_url = None
        if not campaign.voice_preset:
            campaign.voice_preset = None
        campaign.voice_custom_id = (campaign.voice_custom_id or "").strip() or None
        if not campaign.prompt_template:
            campaign.prompt_template = None
        if not campaign.fallback_script:
            campaign.fallback_script = None
        if not campaign.cron_schedule:
            campaign.cron_schedule = None

        db.session.commit()

        # Handle music bed upload / removal
        _handle_music_bed_upload(campaign, form)

        # Update pronunciation entries
        _save_pronunciation_entries(campaign, request.form)

        # Update ad tags
        _save_ad_tags(campaign, request.form)

        flash(f"Campaign '{campaign.name}' updated.", "success")
        return redirect(url_for("admin.campaign_detail", campaign_id=campaign.id))

    return render_template(
        "admin/campaign_form.html",
        form=form,
        editing=True,
        campaign=campaign,
        feed_type_suggestions=_get_feed_type_suggestions(),
    )


# ---- Helpers ----

def _get_feed_type_suggestions() -> list[str]:
    """Return a deduplicated list of feed type suggestions.

    Combines the built-in suggestions with any feed types already used
    in existing campaigns, so the dropdown grows organically.
    """
    from app.models.campaign import FEED_TYPE_SUGGESTIONS

    existing = (
        db.session.query(Campaign.feed_type)
        .distinct()
        .all()
    )
    existing_types = {r[0] for r in existing if r[0]}
    all_types = sorted(set(FEED_TYPE_SUGGESTIONS) | existing_types)
    return all_types


def _save_pronunciation_entries(campaign, form_data):
    """Parse dynamic pronunciation rows from the form and save them.

    Form fields are named: pron_written_0, pron_spoken_0, pron_written_1, ...
    """
    # Delete existing entries
    PronunciationEntry.query.filter_by(campaign_id=campaign.id).delete()

    i = 0
    while True:
        written = form_data.get(f"pron_written_{i}", "").strip()
        spoken = form_data.get(f"pron_spoken_{i}", "").strip()
        if not written and not spoken:
            break
        if written and spoken:
            entry = PronunciationEntry(
                campaign_id=campaign.id,
                written_form=written,
                spoken_form=spoken,
            )
            db.session.add(entry)
        i += 1

    db.session.commit()


def _save_ad_tags(campaign, form_data):
    """Parse ad tag textarea rows from the form and save them.

    Form fields are named: ad_tag_0, ad_tag_1, ...
    """
    tags = []
    i = 0
    while True:
        tag = form_data.get(f"ad_tag_{i}", "").strip()
        if not tag and f"ad_tag_{i}" not in form_data:
            break
        if tag:
            tags.append(tag)
        i += 1

    campaign.ad_tags = tags or None
    db.session.commit()


def _minify_json(value):
    """Return value as compact single-line JSON, or None if blank/invalid."""
    import json
    if not value or not value.strip():
        return None
    try:
        return json.dumps(json.loads(value), separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        return value.strip() or None


def _current_db_admin_id():
    if current_user.is_authenticated and not getattr(current_user, "is_bootstrap", False):
        return current_user.id
    return None


def _is_last_active_db_user(user):
    active_count = AdminUser.query.filter_by(is_active=True).count()
    return user.is_active and active_count <= 1


def _is_current_db_user(user):
    return (
        current_user.is_authenticated
        and not getattr(current_user, "is_bootstrap", False)
        and current_user.id == user.id
    )


logger = logging.getLogger(__name__)

ALLOWED_MUSIC_BED_EXTENSIONS = {"mp3", "wav", "m4a"}


def _handle_music_bed_upload(campaign, form):
    """Process the music bed file upload and removal for a campaign.

    Handles three cases:
    1. User checked "remove" — delete from S3, clear fields.
    2. User uploaded a new file — upload to S3, set fields (delete old first).
    3. Neither — leave existing music bed unchanged.
    """
    # Case 1: Remove existing music bed
    if form.remove_music_bed.data and not form.music_bed_file.data:
        if campaign.music_bed_s3_key and current_app.config.get("S3_ENDPOINT_URL"):
            try:
                from app.storage import s3
                s3.delete(campaign.music_bed_s3_key)
            except Exception:
                logger.warning("Failed to delete old music bed from S3: %s", campaign.music_bed_s3_key)
        campaign.music_bed_s3_key = None
        campaign.music_bed_filename = None
        db.session.commit()
        return

    # Case 2: New file uploaded
    file = form.music_bed_file.data
    if not file:
        return

    filename = secure_filename(file.filename)
    if not filename:
        return

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_MUSIC_BED_EXTENSIONS:
        return

    file_bytes = file.read()

    content_types = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}
    content_type = content_types.get(ext, "audio/mpeg")

    s3_key = f"music-beds/{campaign.id}/{filename}"

    if current_app.config.get("S3_ENDPOINT_URL"):
        # Delete old music bed from S3 if replacing
        if campaign.music_bed_s3_key and campaign.music_bed_s3_key != s3_key:
            try:
                from app.storage import s3
                s3.delete(campaign.music_bed_s3_key)
            except Exception:
                logger.warning("Failed to delete old music bed: %s", campaign.music_bed_s3_key)

        from app.storage import s3
        s3.upload(s3_key, file_bytes, content_type=content_type)
        campaign.music_bed_s3_key = s3_key
        campaign.music_bed_filename = filename
    else:
        # Local fallback for development
        local_dir = os.path.join(current_app.instance_path, "music-beds", str(campaign.id))
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        campaign.music_bed_filename = local_path
        campaign.music_bed_s3_key = None

    db.session.commit()
