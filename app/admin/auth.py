"""Authentication helpers for the admin UI."""

import logging

from flask import current_app
from flask_login import UserMixin
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models import AdminUser

from app.extensions import db, login_manager

logger = logging.getLogger(__name__)


class BootstrapAdminUser(UserMixin):
    """Break-glass admin backed by environment variables."""

    id = "bootstrap:admin"
    email = None
    full_name = "Bootstrap Admin"
    display_name = "Bootstrap Admin"
    must_change_password = False
    is_active = True

    @property
    def is_bootstrap(self):
        return True

    def get_id(self):
        return self.id


def normalize_login(value):
    return (value or "").strip()


def authenticate_database_user(email, password):
    normalized_email = AdminUser.normalize_email(email)
    if not normalized_email or not password:
        return None

    try:
        user = AdminUser.query.filter_by(email=normalized_email).first()
    except (OperationalError, ProgrammingError):
        logger.warning("admin_users table not available — skipping database auth")
        db.session.rollback()
        return None
    if not user or not user.is_active:
        return None
    if not user.check_password(password):
        return None
    return user


def authenticate_bootstrap_user(login_value, password):
    if not password:
        return None

    login_candidate = normalize_login(login_value)
    if (
        login_candidate == current_app.config["ADMIN_USERNAME"]
        and password == current_app.config["ADMIN_PASSWORD"]
    ):
        return BootstrapAdminUser()
    return None


@login_manager.user_loader
def load_user(user_id):
    if user_id == "bootstrap:admin":
        return BootstrapAdminUser()
    if user_id.startswith("user:"):
        raw_id = user_id.split(":", 1)[1]
        if not raw_id.isdigit():
            return None
        try:
            user = db.session.get(AdminUser, int(raw_id))
        except (OperationalError, ProgrammingError):
            logger.warning("admin_users table not available — skipping user load")
            db.session.rollback()
            return None
        if user and user.is_active:
            return user
    return None
