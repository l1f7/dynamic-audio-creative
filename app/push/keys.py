"""Per-advertiser API keys for the desktop daemon."""

import secrets
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import Advertiser, ApiKey
from app.models.api_key import KEY_PREFIX_LENGTH

API_KEY_PREFIX = "dac_"
API_KEY_RANDOM_BYTES = 32
# Keys are 256-bit random secrets, so a long stretch adds nothing; keep /me cheap.
API_KEY_HASH_METHOD = "pbkdf2:sha256:1000"


def generate_plaintext_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_RANDOM_BYTES)


def create_key(advertiser: Advertiser, name: str) -> tuple[ApiKey, str]:
    """Store a new key and return it with the plaintext, which is never stored."""
    plaintext = generate_plaintext_key()
    api_key = ApiKey(
        advertiser_id=advertiser.id,
        name=name,
        key_hash=generate_password_hash(plaintext, method=API_KEY_HASH_METHOD),
        key_prefix=plaintext[:KEY_PREFIX_LENGTH],
    )
    db.session.add(api_key)
    db.session.commit()
    return api_key, plaintext


def revoke_key(api_key: ApiKey) -> None:
    api_key.revoked_at = datetime.now(timezone.utc)
    db.session.commit()


def resolve_key(raw_key: str | None) -> Advertiser | None:
    """Return the active advertiser owning this key, touching last_used_at."""
    api_key = _find_matching_key(raw_key)
    if api_key is None or not api_key.advertiser.is_active:
        return None
    api_key.last_used_at = datetime.now(timezone.utc)
    db.session.commit()
    return api_key.advertiser


def _find_matching_key(raw_key: str | None) -> ApiKey | None:
    if not raw_key:
        return None
    candidates = ApiKey.query.filter_by(
        key_prefix=raw_key[:KEY_PREFIX_LENGTH], revoked_at=None
    ).all()
    for candidate in candidates:
        if check_password_hash(candidate.key_hash, raw_key):
            return candidate
    return None
