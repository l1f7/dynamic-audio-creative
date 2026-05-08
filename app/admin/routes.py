"""Admin blueprint routes — CRUD for advertisers and campaigns."""

from flask import flash, redirect, render_template, request, url_for
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
            tagline=form.tagline.data,
            cta=form.cta.data,
            seasonal_hook=form.seasonal_hook.data,
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

    return render_template("admin/campaign_form.html", form=form, editing=False)


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
    )


# ---- Helpers ----

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
