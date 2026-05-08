"""API routes — trigger ad generation and poll status.

Authenticated via X-API-Key header.
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


@api_bp.route("/campaigns/<int:campaign_id>/generate", methods=["POST"])
def generate(campaign_id):
    """Trigger ad generation for a campaign. Returns the run ID."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    # TODO Phase 3: enqueue RQ job, return run_id
    return jsonify({"error": "Not yet implemented — coming in Phase 3"}), 501


@api_bp.route("/runs/<int:run_id>", methods=["GET"])
def run_status(run_id):
    """Poll the status of an ad run."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    # TODO Phase 3: return run status, script text, audio URL
    return jsonify({"error": "Not yet implemented — coming in Phase 3"}), 501


@api_bp.route("/scheduler/tick", methods=["POST"])
def scheduler_tick():
    """Called by Render cron — checks which campaigns are due and enqueues jobs."""
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    # TODO Phase 5: evaluate cron schedules, enqueue due campaigns
    return jsonify({"message": "Scheduler tick — not yet implemented"}), 200
