"""Admin blueprint routes — CRUD for advertisers and campaigns."""

import os

from flask import flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.admin import admin_bp
from app.admin.auth import AdminUser
from app.admin.forms import AdvertiserForm, CampaignForm, LoginForm
from app.extensions import db
from app.models import AdRun, Advertiser, Campaign, PronunciationEntry


# ---- Auth ----

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        if AdminUser.check_credentials(form.username.data, form.password.data):
            login_user(AdminUser())
            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin.dashboard"))
        flash("Invalid credentials.", "danger")

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


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
            voice_custom_id=form.voice_custom_id.data or None,
            intro_seconds=form.intro_seconds.data,
            outro_seconds=form.outro_seconds.data,
            duck_volume=form.duck_volume.data,
            duck_fade=form.duck_fade.data,
            prompt_template=form.prompt_template.data or None,
            target_seconds=form.target_seconds.data,
            target_words=form.target_words.data,
            cron_schedule=form.cron_schedule.data or None,
        )
        db.session.add(campaign)
        db.session.commit()

        # Save pronunciation entries from form
        _save_pronunciation_entries(campaign, request.form)

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


@admin_bp.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
@login_required
def campaign_edit(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    form = CampaignForm(obj=campaign)
    form.advertiser_id.choices = [
        (a.id, a.name) for a in Advertiser.query.order_by(Advertiser.name).all()
    ]

    if form.validate_on_submit():
        form.populate_obj(campaign)
        # Clear empty strings to None
        if not campaign.feed_url:
            campaign.feed_url = None
        if not campaign.voice_preset:
            campaign.voice_preset = None
        if not campaign.voice_custom_id:
            campaign.voice_custom_id = None
        if not campaign.prompt_template:
            campaign.prompt_template = None
        if not campaign.cron_schedule:
            campaign.cron_schedule = None

        db.session.commit()

        # Update pronunciation entries
        _save_pronunciation_entries(campaign, request.form)

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
