"""Flask application factory."""

import os

from flask import Flask

from app.extensions import db, migrate, login_manager


def create_app(config_name=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load config
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    if config_name == "production":
        app.config.from_object("app.config.ProductionConfig")
    elif config_name == "testing":
        app.config.from_object("app.config.TestingConfig")
    else:
        app.config.from_object("app.config.DevelopmentConfig")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Register blueprints
    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    # Root redirect
    @app.route("/")
    def index():
        from flask import redirect, url_for
        return redirect(url_for("admin.dashboard"))

    return app
