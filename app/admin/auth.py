"""Simple admin authentication — env-var credentials for MVP."""

from flask import current_app
from flask_login import UserMixin

from app.extensions import login_manager


class AdminUser(UserMixin):
    """Single admin user backed by env vars. No database table needed."""

    def __init__(self):
        self.id = "admin"

    @staticmethod
    def check_credentials(username, password):
        return (
            username == current_app.config["ADMIN_USERNAME"]
            and password == current_app.config["ADMIN_PASSWORD"]
        )


@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        return AdminUser()
    return None
