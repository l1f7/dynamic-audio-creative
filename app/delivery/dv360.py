"""Display & Video 360 (DV360) delivery.

Two-step workflow:
  1. Upload  — POST /upload/v4/advertisers/{advertiserId}/assets?uploadType=multipart
               Returns a mediaId.
  2. Creative — POST /v4/advertisers/{advertiserId}/creatives
               Links the mediaId as ASSET_ROLE_MAIN.

Authentication: OAuth 2.0 service account. The service account JSON and DV360
advertiser ID are stored per-advertiser in the admin UI (Advertiser model).
Each advertiser can have its own Google Cloud service account.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import requests
from flask import current_app

logger = logging.getLogger(__name__)

_UPLOAD_URL = (
    "https://displayvideo.googleapis.com/upload/v4/advertisers/{advertiser_id}/assets"
)
_CREATIVES_URL = (
    "https://displayvideo.googleapis.com/v4/advertisers/{advertiser_id}/creatives"
)
_LINE_ITEM_URL = (
    "https://displayvideo.googleapis.com/v4/advertisers/{advertiser_id}/lineItems/{line_item_id}"
)
_SCOPE = "https://www.googleapis.com/auth/display-video"


class DV360DeliveryError(Exception):
    """Raised when any step of the DV360 delivery workflow fails."""


class DV360NotConfiguredError(Exception):
    """Raised when required DV360 config or advertiser credentials are missing."""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_delivery_available() -> bool:
    """Return True if DV360 delivery is globally enabled."""
    try:
        return bool(current_app.config.get("DV360_ENABLED"))
    except RuntimeError:
        return False


def deliver_ad(ad_run, final_ad_bytes: bytes) -> str:
    """Run the full two-step DV360 delivery workflow.

    Returns the created creative resource name (e.g. advertisers/123/creatives/456).
    """
    advertiser = ad_run.campaign.advertiser

    dv360_advertiser_id = advertiser.dv360_advertiser_id
    if not dv360_advertiser_id:
        raise DV360NotConfiguredError(
            f"Advertiser '{advertiser.name}' has no DV360 advertiser ID configured."
        )

    service_account_json = advertiser.dv360_service_account_json
    if not service_account_json:
        raise DV360NotConfiguredError(
            f"Advertiser '{advertiser.name}' has no DV360 service account configured."
        )

    line_item_id = ad_run.campaign.dv360_line_item_id
    if not line_item_id:
        raise DV360NotConfiguredError(
            f"Campaign '{ad_run.campaign.name}' has no DV360 line item ID configured."
        )

    logger.info("[DV360] Starting delivery for ad_run #%s", ad_run.id)
    logger.info(
        "[DV360] advertiser_id=%s  line_item_id=%s",
        dv360_advertiser_id,
        line_item_id,
    )

    try:
        sa_email = json.loads(service_account_json).get("client_email", "<unknown>")
    except Exception:
        sa_email = "<invalid JSON>"
    logger.info("[DV360] service_account_email=%s", sa_email)

    access_token = _get_access_token(service_account_json)
    logger.info("[DV360] OAuth token obtained")

    # Step 1: Upload audio asset
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"ad_{ad_run.id}_{ts}.mp3"
    upload_url = _UPLOAD_URL.format(advertiser_id=dv360_advertiser_id)
    logger.info(
        "[DV360] Step 1: upload asset — POST %s  filename=%s  size=%d bytes",
        upload_url,
        filename,
        len(final_ad_bytes),
    )
    media_id = _upload_asset(access_token, dv360_advertiser_id, filename, final_ad_bytes)
    logger.info("[DV360] Step 1 OK — media_id=%s", media_id)

    # Step 2: Create audio creative
    display_name = f"{ad_run.campaign.name} — Run #{ad_run.id} — {ts}"
    website = advertiser.website or ""
    if website and not website.startswith("http"):
        website = f"https://{website}"
    click_url = website or "https://example.com"
    creatives_url = _CREATIVES_URL.format(advertiser_id=dv360_advertiser_id)
    logger.info(
        "[DV360] Step 2: create creative — POST %s  display_name=%s  media_id=%s  click_url=%s",
        creatives_url,
        display_name,
        media_id,
        click_url,
    )
    creative_name, creative_id = _create_creative(
        access_token, dv360_advertiser_id, display_name, media_id, click_url
    )
    logger.info("[DV360] Step 2 OK — creative_name=%s  creative_id=%s", creative_name, creative_id)

    # Step 3: Assign creative to line item (replaces previous assignment)
    line_item_url = _LINE_ITEM_URL.format(advertiser_id=dv360_advertiser_id, line_item_id=line_item_id)
    logger.info(
        "[DV360] Step 3: assign creative — PATCH %s  creative_id=%s",
        line_item_url,
        creative_id,
    )
    _assign_creative(access_token, dv360_advertiser_id, line_item_id, creative_id)
    logger.info("[DV360] Step 3 OK — creative assigned and active")
    logger.info("[DV360] Delivery complete for ad_run #%s", ad_run.id)

    return creative_name


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _get_access_token(service_account_json: str) -> str:
    """Obtain a short-lived OAuth 2.0 access token from a service account JSON string."""
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
    except ImportError as exc:
        raise DV360NotConfiguredError(
            "google-auth is not installed. Add 'google-auth' to requirements.txt."
        ) from exc

    try:
        creds_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise DV360NotConfiguredError(
            f"DV360 service account JSON is not valid JSON: {exc}"
        ) from exc

    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=[_SCOPE]
    )
    creds.refresh(GoogleRequest())
    return creds.token


def _upload_asset(
    access_token: str,
    advertiser_id: str,
    filename: str,
    audio_bytes: bytes,
) -> str:
    """Upload the audio file as a DV360 asset. Returns the mediaId string."""
    url = _UPLOAD_URL.format(advertiser_id=advertiser_id)
    body, content_type = _build_multipart_related(
        metadata={"filename": filename},
        media_bytes=audio_bytes,
        media_type="audio/mpeg",
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": content_type,
    }
    resp = requests.post(
        url,
        params={"uploadType": "multipart"},
        headers=headers,
        data=body,
        timeout=120,
    )
    logger.info(
        "[DV360] _upload_asset HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "upload asset")
    data = resp.json()
    try:
        return data["asset"]["mediaId"]
    except (KeyError, TypeError) as exc:
        raise DV360DeliveryError(
            f"DV360 upload response missing asset.mediaId: {data}"
        ) from exc


def _create_creative(
    access_token: str,
    advertiser_id: str,
    display_name: str,
    media_id: str,
    click_url: str,
) -> tuple[str, str]:
    """Create a DV360 audio creative object. Returns (resource_name, creative_id)."""
    url = _CREATIVES_URL.format(advertiser_id=advertiser_id)
    body = {
        "displayName": display_name,
        "creativeType": "CREATIVE_TYPE_AUDIO",
        "hostingSource": "HOSTING_SOURCE_HOSTED",
        "assets": [
            {
                "asset": {"mediaId": media_id},
                "role": "ASSET_ROLE_MAIN",
            }
        ],
        "exitEvents": [
            {
                "type": "EXIT_EVENT_TYPE_DEFAULT",
                "url": click_url,
                "name": "default",
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=body, headers=headers, timeout=30)
    logger.info(
        "[DV360] _create_creative HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "create creative")
    data = resp.json()
    creative_name = data.get("name", f"advertisers/{advertiser_id}/creatives/{media_id}")
    # Resource name format: "advertisers/{advertiserId}/creatives/{creativeId}"
    creative_id = data.get("creativeId") or creative_name.split("/")[-1]
    return creative_name, creative_id


def _assign_creative(
    access_token: str,
    advertiser_id: str,
    line_item_id: str,
    creative_id: str,
) -> None:
    """Assign the creative to a line item, replacing any previous assignment."""
    url = _LINE_ITEM_URL.format(advertiser_id=advertiser_id, line_item_id=line_item_id)
    body = {
        "creativeIds": [creative_id],
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.patch(
        url,
        params={"updateMask": "creativeIds"},
        json=body,
        headers=headers,
        timeout=30,
    )
    logger.info(
        "[DV360] _assign_creative HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "assign creative to line item")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _build_multipart_related(
    metadata: dict,
    media_bytes: bytes,
    media_type: str,
) -> tuple[bytes, str]:
    """Build a multipart/related body suitable for Google API media uploads."""
    boundary = uuid.uuid4().hex
    metadata_json = json.dumps(metadata).encode("utf-8")

    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        metadata_json,
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        f"Content-Type: {media_type}\r\n\r\n".encode(),
        media_bytes,
        b"\r\n",
        f"--{boundary}--".encode(),
    ])

    return body, f"multipart/related; boundary={boundary}"


def _raise_for_status(resp: requests.Response, step: str) -> None:
    if not resp.ok:
        raise DV360DeliveryError(
            f"DV360 {step} failed: HTTP {resp.status_code} — {resp.text[:500]}"
        )
