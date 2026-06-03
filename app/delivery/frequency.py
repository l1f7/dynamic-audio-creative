"""Frequency Campaign Manager API delivery.

Five-step workflow:
  1. Validate  — GET  /campaign/validate/{client}/{token}
  2. New draft — POST /application/{appId}/draft
  3. Upload    — POST /campaign/{campaignId}/upload-creative  (multipart)
  4. Attach    — POST /application/{appId}/draft/{draftId}/creative
  5. Publish   — POST /application/{appId}/draft/{draftId}/publish

Authentication: step 1 returns a `sid` session cookie. All subsequent requests
pass it explicitly via cookies= to avoid requests cookie-jar policy issues.
"""

import io
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from flask import current_app

logger = logging.getLogger(__name__)


class FrequencyDeliveryError(Exception):
    """Raised when any step of the Frequency delivery workflow fails."""


class FrequencyNotConfiguredError(Exception):
    """Raised when required Frequency config or advertiser credentials are missing."""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_delivery_available() -> bool:
    """Return True if Frequency delivery is globally enabled and the base URL is set."""
    try:
        cfg = current_app.config
        return bool(cfg.get("FREQUENCY_ENABLED") and cfg.get("CMPAPI_BASE_URL"))
    except RuntimeError:
        return False


def deliver_ad(ad_run, final_ad_bytes: bytes) -> str:
    """Run the full five-step Frequency delivery workflow."""
    cfg = current_app.config
    base_url = cfg.get("CMPAPI_BASE_URL", "").rstrip("/")
    app_id = ad_run.campaign.frequency_app_id

    logger.info("[Frequency] Starting delivery for ad_run #%s", ad_run.id)
    logger.info("[Frequency] base_url=%s  app_id=%s", base_url, app_id)

    if not base_url:
        raise FrequencyNotConfiguredError("CMPAPI_BASE_URL must be set to deliver ads.")

    if not app_id:
        raise FrequencyNotConfiguredError(
            f"Campaign '{ad_run.campaign.name}' has no Frequency app ID configured."
        )

    advertiser = ad_run.campaign.advertiser
    client = advertiser.frequency_client
    token = advertiser.frequency_token

    logger.info(
        "[Frequency] advertiser=%s  client=%s  token=%s",
        advertiser.name,
        client,
        "***" if token else None,
    )

    if not client or not token:
        raise FrequencyNotConfiguredError(
            f"Advertiser '{advertiser.name}' has no Frequency client/token configured."
        )

    # --- Step 1: Validate ---
    logger.info(
        "[Frequency] Step 1: validate — GET %s/campaign/validate/%s/<token>",
        base_url,
        client,
    )
    validate_resp = _validate(base_url, client, token)
    validate_data = validate_resp.json()
    logger.info("[Frequency] Step 1 response: %s", validate_data)
    campaign_id = validate_data["tokenData"]["campaign_id"]

    auth_token = validate_data.get("authToken")
    if not auth_token:
        raise FrequencyDeliveryError(
            "Frequency validate response missing 'authToken'. Cannot authenticate subsequent steps."
        )

    vast_urls = {v["version"]: v["url"] for v in validate_data.get("vastUrls", [])}
    for version, url in vast_urls.items():
        logger.info("[Frequency] VAST %s: %s", version, url)
    logger.info("[Frequency] Step 1 OK — campaign_id=%s  authToken=set", campaign_id)

    auth_headers = {"Authorization": f"Bearer {auth_token}"}
    auth_cookies = {}

    # --- Step 2: Create draft ---
    logger.info(
        "[Frequency] Step 2: create draft — POST %s/application/%s/draft",
        base_url,
        app_id,
    )
    draft_data = _create_draft(base_url, app_id, auth_headers, auth_cookies)
    logger.info("[Frequency] Step 2 response: %s", draft_data)
    draft_id = draft_data["id"]
    logger.info("[Frequency] Step 2 OK — draft_id=%s", draft_id)

    # --- Step 3: Upload creative ---
    duration_secs = _probe_duration(final_ad_bytes)
    logger.info(
        "[Frequency] Step 3: upload creative — POST %s/campaign/%s/upload-creative  "
        "file_size=%d bytes  duration=%ds  app_id=%s",
        base_url,
        campaign_id,
        len(final_ad_bytes),
        duration_secs,
        app_id,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"ad_{ad_run.id}_{ts}.mp3"
    creative_data = _upload_creative(
        base_url, app_id, campaign_id, final_ad_bytes, duration_secs, auth_headers, auth_cookies,
        filename=filename,
    )
    logger.info("[Frequency] Step 3 response: %s", creative_data)
    logger.info(
        "[Frequency] Step 3 OK — name=%s  url=%s",
        creative_data.get("name"),
        creative_data.get("url"),
    )

    # --- Step 4: Attach creative to draft ---
    attach_body = {
        "fileName": creative_data["name"],
        "fileUrl": creative_data["url"],
        "type": "audio",
        "serveOption": "random",
        "fileWeight": 100,
        "rowIndex": 0,
    }
    logger.info(
        "[Frequency] Step 4: attach creative — POST %s/application/%s/draft/%s/creative  body=%s",
        base_url,
        app_id,
        draft_id,
        attach_body,
    )
    _attach_creative(base_url, app_id, draft_id, creative_data, auth_headers, auth_cookies)
    logger.info("[Frequency] Step 4 OK")

    # --- Step 5: Publish ---
    publish_date = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    logger.info(
        "[Frequency] Step 5: publish draft — POST %s/application/%s/draft/%s/publish  "
        "schedulePublishDate=%s",
        base_url,
        app_id,
        draft_id,
        publish_date,
    )
    vast_xml = _publish_draft(base_url, app_id, draft_id, auth_headers, auth_cookies)
    logger.info("[Frequency] Step 5 response (first 500 chars): %s", vast_xml[:500])
    logger.info("[Frequency] Delivery complete for ad_run #%s", ad_run.id)

    return vast_xml


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _validate(base_url: str, client: str, token: str) -> requests.Response:
    url = f"{base_url}/campaign/validate/{quote(client, safe='')}/{quote(token, safe='')}"
    resp = requests.get(url, timeout=30)
    logger.info("[Frequency] _validate HTTP %s — %s", resp.status_code, resp.text[:500])
    _raise_for_status(resp, "validate")
    return resp


def _create_draft(base_url: str, app_id: str, headers: dict, cookies: dict) -> dict:
    url = f"{base_url}/application/{app_id}/draft"
    resp = requests.post(url, json={}, headers=headers, cookies=cookies, timeout=30)
    logger.info(
        "[Frequency] _create_draft HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "create draft")
    return resp.json()


def _upload_creative(
    base_url: str,
    app_id: str,
    campaign_id,
    audio_bytes: bytes,
    duration_secs: int,
    headers: dict,
    cookies: dict,
    filename: str = "ad.mp3",
) -> dict:
    url = f"{base_url}/campaign/{campaign_id}/upload-creative"
    files = {
        "file": (filename, io.BytesIO(audio_bytes), "audio/mpeg"),
    }
    data = {
        "duration": str(duration_secs),
        "applicationId": str(app_id),
    }
    resp = requests.post(url, files=files, data=data, headers=headers, cookies=cookies, timeout=120)
    logger.info(
        "[Frequency] _upload_creative HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "upload creative")
    return resp.json()


def _attach_creative(
    base_url: str,
    app_id: str,
    draft_id,
    creative_data: dict,
    headers: dict,
    cookies: dict,
) -> None:
    url = f"{base_url}/application/{app_id}/draft/{draft_id}/creative"
    body = {
        "fileName": creative_data["name"],
        "fileUrl": creative_data["url"],
        "type": "audio",
        "serveOption": "random",
        "fileWeight": 100,
        "rowIndex": 0,
    }
    resp = requests.post(url, json=body, headers=headers, cookies=cookies, timeout=30)
    logger.info(
        "[Frequency] _attach_creative HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "attach creative")


def _publish_draft(
    base_url: str, app_id: str, draft_id, headers: dict, cookies: dict
) -> str:
    url = f"{base_url}/application/{app_id}/draft/{draft_id}/publish"
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    body = {"schedulePublishDate": today}
    resp = requests.post(url, json=body, headers=headers, cookies=cookies, timeout=30)
    logger.info(
        "[Frequency] _publish_draft HTTP %s — %s", resp.status_code, resp.text[:500]
    )
    _raise_for_status(resp, "publish draft")
    return resp.text


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _raise_for_status(resp: requests.Response, step: str) -> None:
    if not resp.ok:
        raise FrequencyDeliveryError(
            f"Frequency {step} failed: HTTP {resp.status_code} — {resp.text[:500]}"
        )


def _probe_duration(audio_bytes: bytes) -> int:
    """Return the duration of an MP3 in whole seconds using ffprobe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ad.mp3"
        path.write_bytes(audio_bytes)
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = int(float(result.stdout.strip()))
            logger.info("[Frequency] Probed audio duration: %ds", duration)
            return duration
        except (subprocess.CalledProcessError, ValueError) as exc:
            raise FrequencyDeliveryError(
                f"Could not determine audio duration: {exc}"
            ) from exc
