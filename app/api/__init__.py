"""API blueprint — JSON endpoints for triggers and status."""

from flask import Blueprint

api_bp = Blueprint("api", __name__)

from app.api import routes  # noqa: E402, F401
from app.api import scoreproxy  # noqa: E402, F401
