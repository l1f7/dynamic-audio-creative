"""Read the Frequency token's JWT payload.

The token identifies an ad unit. We are not its issuer, so the signature is not
verified — only the payload is decoded, to learn what the token points at.
"""

import base64
import binascii
import json

JWT_SEGMENTS = 3
PAYLOAD_INDEX = 1
BASE64_BLOCK = 4

DISPLAY_FIELDS = (
    ("advertiser_name", "Advertiser"),
    ("campaign_name", "Campaign"),
    ("flight_name", "Flight"),
    ("creative_type", "Creative type"),
    ("creative_duration", "Creative duration (s)"),
    ("cm_unit_id", "Ad unit ID"),
)


class InvalidFrequencyToken(ValueError):
    """The token is not a JWT with a JSON object payload."""


def decode_payload(token: str) -> dict:
    parts = (token or "").strip().split(".")
    if len(parts) != JWT_SEGMENTS:
        raise InvalidFrequencyToken("Frequency token must be a JWT with three dot-separated parts")
    try:
        payload = json.loads(_b64url_decode(parts[PAYLOAD_INDEX]))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidFrequencyToken("Frequency token payload is not valid base64 JSON") from exc
    if not isinstance(payload, dict):
        raise InvalidFrequencyToken("Frequency token payload is not a JSON object")
    return payload


def creative_duration(token: str | None) -> float | None:
    """Expected creative length in seconds, or None when the token does not say."""
    if not token:
        return None
    try:
        raw = decode_payload(token).get("creative_duration")
        return float(raw) if raw not in (None, "") else None
    except (InvalidFrequencyToken, TypeError, ValueError):
        return None


def summarise(payload: dict) -> list[tuple[str, str]]:
    """(label, value) pairs for the admin UI, in display order."""
    return [(label, str(payload[key])) for key, label in DISPLAY_FIELDS if key in payload]


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % BASE64_BLOCK)
    return base64.urlsafe_b64decode(segment + padding)
