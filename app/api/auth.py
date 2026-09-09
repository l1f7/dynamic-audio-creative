"""X-API-Key handling for /api/v1.

Per-advertiser keys (app.push.keys) are the norm. The single global API_KEY
survives only for the Render cron hitting /scheduler/tick.
"""

from functools import wraps

from flask import current_app, g, jsonify, request

from app.push.keys import resolve_key

API_KEY_HEADER = "X-API-Key"


def _unauthorized():
    return jsonify({"error": "Unauthorized"}), 401


def require_advertiser_key(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        advertiser = resolve_key(request.headers.get(API_KEY_HEADER))
        if advertiser is None:
            return _unauthorized()
        g.advertiser = advertiser
        return view(*args, **kwargs)
    return wrapped


def require_global_api_key(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = current_app.config.get("API_KEY")
        if not expected or request.headers.get(API_KEY_HEADER) != expected:
            return _unauthorized()
        return view(*args, **kwargs)
    return wrapped
