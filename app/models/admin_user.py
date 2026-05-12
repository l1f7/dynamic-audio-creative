"""Database-backed admin users for the Flask admin UI."""

from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    full_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())
    created_by_user_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"), nullable=True
    )

    created_by_user = db.relationship(
        "AdminUser",
        remote_side=[id],
        backref=db.backref("created_users", lazy="dynamic"),
    )

    @validates("email")
    def _normalize_email(self, _key, value):
        return self.normalize_email(value)

    @staticmethod
    def normalize_email(value):
        return (value or "").strip().lower()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"user:{self.id}"

    @property
    def display_name(self):
        return self.full_name or self.email

    @property
    def is_bootstrap(self):
        return False

    def __repr__(self):
        return f"<AdminUser {self.id}: {self.email}>"
