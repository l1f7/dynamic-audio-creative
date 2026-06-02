"""Flask configuration classes."""

import os

from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    """Shared configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB upload limit

    # API keys
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

    # S3-compatible storage (provider-agnostic)
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")
    S3_BUCKET = os.environ.get("S3_BUCKET", "dynamic-audio")
    S3_REGION = os.environ.get("S3_REGION", "auto")

    # Redis (for RQ background jobs)
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Internal API key for cron/machine-to-machine calls
    API_KEY = os.environ.get("API_KEY")

    # Admin credentials (simple env-var auth for MVP)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

    # Claude model
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    # ElevenLabs model
    ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_monolingual_v1")

    # Frequency Campaign Manager API
    FREQUENCY_ENABLED = os.environ.get("FREQUENCY_ENABLED", "false").lower() == "true"
    CMPAPI_BASE_URL = os.environ.get("CMPAPI_BASE_URL")   # e.g. https://cmpapi.example.com
    # Note: app ID is configured per-campaign via Campaign.frequency_app_id


class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///dev.db"
    )


class ProductionConfig(BaseConfig):
    """Production configuration."""
    DEBUG = False

    @staticmethod
    def _fix_database_url(url):
        """Render provides postgres:// but SQLAlchemy 2.0 requires postgresql://."""
        if url and url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        return url

    SQLALCHEMY_DATABASE_URI = _fix_database_url.__func__(os.environ.get("DATABASE_URL"))


class TestingConfig(BaseConfig):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False  # disable CSRF for test form submissions
