"""API routes — trigger ad generation and poll status.

Authenticated via X-API-Key header.

Testing flags (query params):
  testing=true          Enable fake responses (only honoured in non-production)
  error=4XX             Return a 400 Bad Request
  error=5XX             Return a 500 Internal Server Error
  error=empty           Return a 200 with an empty/no-data payload
  error=failedatsource  Return a 502 simulating an upstream feed failure
"""

from flask import current_app, jsonify, request

from app.api import api_bp


def _check_api_key():
    """Verify the X-API-Key header matches the configured API key."""
    key = request.headers.get("X-API-Key")
    expected = current_app.config.get("API_KEY")
    if not expected or key != expected:
        return jsonify({"error": "Unauthorized"}), 401
    return None


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
def generate(campaign_id):
    """Trigger ad generation for a campaign. Returns the run ID."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    fake = _check_testing_flags()
    if fake:
        return fake

    # TODO Phase 3: enqueue RQ job, return run_id
    return jsonify({"error": "Not yet implemented — coming in Phase 3"}), 501


@api_bp.route("/runs/<int:run_id>", methods=["GET"])
def run_status(run_id):
    """Poll the status of an ad run."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    fake = _check_testing_flags()
    if fake:
        return fake

    # TODO Phase 3: return run status, script text, audio URL
    return jsonify({"error": "Not yet implemented — coming in Phase 3"}), 501


@api_bp.route("/scheduler/tick", methods=["POST"])
def scheduler_tick():
    """Called by Render cron — checks which campaigns are due and enqueues jobs."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    fake = _check_testing_flags()
    if fake:
        return fake

    # TODO Phase 5: evaluate cron schedules, enqueue due campaigns
    return jsonify({"message": "Scheduler tick — not yet implemented"}), 200
