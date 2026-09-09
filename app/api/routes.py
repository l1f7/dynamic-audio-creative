"""API routes — trigger ad generation and the scheduler tick.

Per-advertiser push endpoints live in app.api.push. The global API_KEY is
accepted only by /scheduler/tick, which Render cron calls.

Testing flags (query params):
  testing=true          Enable fake responses (only honoured in non-production)
  error=4XX             Return a 400 Bad Request
  error=5XX             Return a 500 Internal Server Error
  error=empty           Return a 200 with an empty/no-data payload
  error=failedatsource  Return a 502 simulating an upstream feed failure
"""

from flask import current_app, g, jsonify, request

from app.api import api_bp
from app.api.auth import require_advertiser_key, require_global_api_key
from app.models import Campaign


def _check_testing_flags():
    """Return a fake response if testing flags are present, otherwise None.

    Only active when the query param ``testing=true`` is set AND the app is
    not running in production (ENV != 'production').
    """
    if request.args.get("testing") != "true":
        return None
    if current_app.config.get("ENV") == "production":
        return None

    error = request.args.get("error", "").lower()

    if error.startswith("4"):
        return jsonify({"error": "Simulated 4XX client error", "testing": True}), 400

    if error.startswith("5"):
        return jsonify({"error": "Simulated 5XX server error", "testing": True}), 500

    if error == "empty":
        return jsonify({"data": [], "testing": True}), 200

    if error == "failedatsource":
        return jsonify({"error": "Upstream feed request failed", "testing": True}), 502

    return None


@api_bp.route("/campaigns/<int:campaign_id>/generate", methods=["POST"])
@require_advertiser_key
def generate(campaign_id):
    """Trigger ad generation for a campaign. Returns the run ID."""
    fake = _check_testing_flags()
    if fake:
        return fake

    campaign = Campaign.query.filter_by(id=campaign_id, advertiser_id=g.advertiser.id).first()
    if campaign is None:
        return jsonify({"error": "Campaign not found"}), 404

    # TODO Phase 3: enqueue RQ job, return run_id
    return jsonify({"error": "Not yet implemented — coming in Phase 3"}), 501


@api_bp.route("/scheduler/tick", methods=["POST"])
@require_global_api_key
def scheduler_tick():
    """Called by Render cron. Delivers pushed runs that are waiting."""
    fake = _check_testing_flags()
    if fake:
        return fake

    from app.jobs.scheduler import deliver_pending_pushes
    delivered = deliver_pending_pushes()
    return jsonify({"delivered_pushes": delivered}), 200
