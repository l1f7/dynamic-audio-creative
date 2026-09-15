"""Desktop push mode endpoints, keyed by per-advertiser X-API-Key.

See docs/dac-api-contract.md. The daemon retries 5xx and 429 only, so anything
transient must not be a 4xx, and 422 means "the file is wrong" (dead-letter).
"""

import re
from datetime import timezone

from botocore.exceptions import ClientError
from flask import Response, abort, g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.api import api_bp
from app.api.auth import require_advertiser_key
from app.extensions import db
from app.models import AdRun, Campaign
from app.models.campaign import CAMPAIGN_TYPE_PUSH
from app.push import service
from app.push.audio import PushRejected
from app.storage import s3

CONTENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_BAD_GATEWAY = 502
HTTP_UNAVAILABLE = 503


# ---------------------------------------------------------------------------
# Request plumbing
# ---------------------------------------------------------------------------


@api_bp.errorhandler(HTTPException)
def _json_http_error(exc):
    return jsonify({"error": exc.description}), exc.code


def _visible_campaign(campaign_id: int) -> Campaign:
    """A key reaches only its own advertiser's active push campaigns.

    Automated campaigns are deliberately 404 rather than 403: the daemon has
    no business knowing they exist, and a type change should read to it as
    the campaign simply going away.
    """
    campaign = Campaign.query.filter_by(
        id=campaign_id,
        advertiser_id=g.advertiser.id,
        is_active=True,
        campaign_type=CAMPAIGN_TYPE_PUSH,
    ).first()
    if campaign is None:
        abort(404, "Campaign not found")
    return campaign


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, "JSON object body required")
    return body


def _required(body: dict, field: str):
    value = body.get(field)
    if value in (None, ""):
        abort(400, f"'{field}' is required")
    return value


def _valid_hash(body: dict) -> str:
    content_hash = str(_required(body, "content_hash")).lower()
    if not CONTENT_HASH_PATTERN.match(content_hash):
        abort(400, "'content_hash' must be 64 lowercase hex characters")
    return content_hash


def _rejected(reason: str) -> Response:
    """422 with the reason as plain text: the desktop app shows it verbatim."""
    return Response(reason, status=HTTP_UNPROCESSABLE, mimetype="text/plain")


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _iso_utc(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO_UTC_FORMAT)


def _campaign_json(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "advertiser_name": campaign.advertiser.name,
        "delivery_enabled": bool(campaign.delivery_enabled),
        "deliverable": service.is_deliverable(campaign),
    }


def _run_status_json(run: AdRun) -> dict:
    # Only a finished run has a delivery verdict. A re-queued one keeps its
    # previous failed attempt as history, but nothing is wrong with it *now*,
    # and the daemon would otherwise show a stale error beside a live retry.
    return {
        "run_id": run.id,
        "status": run.status,
        "delivery_error": run.delivery_error if run.is_terminal else None,
    }


def _history_json(run: AdRun, active_id: int | None) -> dict:
    return {
        "run_id": run.id,
        "filename": run.source_filename or run.final_ad_s3_key.rsplit("/", 1)[-1],
        "delivered_at": _iso_utc(run.delivered_at),
        "status": run.status,
        "is_active": run.id == active_id,
        "error": run.delivery_error or run.error_message,
    }


# ---------------------------------------------------------------------------
# Identity and listing
# ---------------------------------------------------------------------------


@api_bp.route("/me", methods=["GET"])
@require_advertiser_key
def me():
    return jsonify({"advertiser_id": g.advertiser.id, "advertiser_name": g.advertiser.name})


@api_bp.route("/campaigns", methods=["GET"])
@require_advertiser_key
def list_campaigns():
    """Push campaigns for this key's advertiser — the drop app's whole registry."""
    campaigns = (
        Campaign.query.filter_by(
            advertiser_id=g.advertiser.id,
            is_active=True,
            campaign_type=CAMPAIGN_TYPE_PUSH,
        )
        .order_by(Campaign.name)
        .all()
    )
    return jsonify([_campaign_json(c) for c in campaigns])


# ---------------------------------------------------------------------------
# Upload and push
# ---------------------------------------------------------------------------


@api_bp.route("/campaigns/<int:campaign_id>/uploads", methods=["POST"])
@require_advertiser_key
def request_upload(campaign_id):
    campaign = _visible_campaign(campaign_id)
    body = _json_body()
    content_hash = _valid_hash(body)
    filename = str(_required(body, "filename"))
    content_type = str(_required(body, "content_type"))

    duplicate = service.find_delivered_run(campaign, content_hash)
    if duplicate:
        return jsonify({"duplicate_run_id": duplicate.id})

    if not s3.is_configured():
        abort(HTTP_UNAVAILABLE, "Object storage is not configured")
    upload_key = service.upload_key_for(campaign, content_hash, filename)
    upload_url = s3.generate_upload_url(upload_key, content_type, service.UPLOAD_URL_TTL_SECONDS)
    return jsonify({"upload_url": upload_url, "upload_key": upload_key})


@api_bp.route("/campaigns/<int:campaign_id>/push", methods=["POST"])
@require_advertiser_key
def push(campaign_id):
    campaign = _visible_campaign(campaign_id)
    body = _json_body()
    content_hash = _valid_hash(body)
    upload_key = str(_required(body, "upload_key"))
    filename = str(_required(body, "filename"))
    if not service.owns_upload_key(campaign, content_hash, upload_key):
        abort(400, "'upload_key' does not belong to this campaign and hash")

    existing = service.find_run(campaign, content_hash)
    if existing:
        service.requeue_failed_run(existing)
        return jsonify({"run_id": existing.id})

    try:
        prepared = service.prepare_pushed_audio(campaign, upload_key, filename)
    except PushRejected as exc:
        return _rejected(str(exc))
    except ClientError as exc:
        abort(400, f"Uploaded object not found: {exc}")

    run = service.register_pushed_run(campaign, prepared, content_hash, filename)
    return jsonify({"run_id": run.id})


# ---------------------------------------------------------------------------
# Status and history
# ---------------------------------------------------------------------------


@api_bp.route("/runs/<int:run_id>", methods=["GET"])
@require_advertiser_key
def run_status(run_id):
    run = (
        AdRun.query.join(Campaign)
        .filter(
            AdRun.id == run_id,
            Campaign.advertiser_id == g.advertiser.id,
            Campaign.campaign_type == CAMPAIGN_TYPE_PUSH,
        )
        .first()
    )
    if run is None:
        abort(404, "Run not found")
    return jsonify(_run_status_json(run))


@api_bp.route("/campaigns/<int:campaign_id>/runs", methods=["GET"])
@require_advertiser_key
def campaign_runs(campaign_id):
    campaign = _visible_campaign(campaign_id)
    active_id = service.active_run_id(campaign)
    runs = campaign.ad_runs.filter(AdRun.final_ad_s3_key.isnot(None)).all()
    return jsonify([_history_json(run, active_id) for run in runs])


# ---------------------------------------------------------------------------
# Revert and pause
# ---------------------------------------------------------------------------


@api_bp.route("/campaigns/<int:campaign_id>/revert", methods=["POST"])
@require_advertiser_key
def revert(campaign_id):
    """Re-deliver a previous run's stored audio. The run keeps its id."""
    from app.delivery.targets import FrequencyTarget
    from app.pipeline.runner import redeliver

    campaign = _visible_campaign(campaign_id)
    source = campaign.ad_runs.filter(AdRun.id == _required(_json_body(), "run_id")).first()
    if source is None:
        abort(404, "Run not found")
    if source.delivered_at is None or not source.final_ad_s3_key:
        abort(HTTP_CONFLICT, "Run was never delivered")
    if not campaign.delivery_enabled:
        abort(HTTP_CONFLICT, "Campaign is paused")

    target = FrequencyTarget()
    unconfigured = target.unconfigured_reason(campaign)
    if unconfigured:
        abort(HTTP_CONFLICT, unconfigured)
    if target.unavailable_reason():
        abort(HTTP_UNAVAILABLE, "Frequency delivery is not enabled on this server")

    redeliver(source.id, deliver_frequency=True)
    db.session.refresh(source)
    if source.delivery_error:
        abort(HTTP_BAD_GATEWAY, source.delivery_error)
    return jsonify({"run_id": source.id})


@api_bp.route("/campaigns/<int:campaign_id>/pause", methods=["POST"])
@require_advertiser_key
def pause(campaign_id):
    """Soft pause: stop future deliveries by flipping delivery_enabled.

    Frequency exposes no pause endpoint and fileWeight has minimum 1, so the
    creative cannot be weighted to zero. A hard pause would mean publishing a
    draft that omits our creative and recording what was removed so resume is
    exact. That is a real publish, far more visible than a pause should be, so
    it is deliberately unimplemented until Frequency confirms whether an
    undocumented ad-unit pause exists.
    """
    campaign = _visible_campaign(campaign_id)
    paused = _json_body().get("paused")
    if not isinstance(paused, bool):
        abort(400, "'paused' must be a boolean")
    campaign.delivery_enabled = not paused
    db.session.commit()
    return jsonify({})
