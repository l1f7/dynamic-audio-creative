"""Frequency Campaign Manager API delivery.

Five-step workflow:
  1. Validate  — GET  /campaign/validate/{client}/{token}
  2. New draft — POST /application/{appId}/draft
     2b. Inspect — GET /application/{appId}/draft/{draftId}/creatives
  3. Upload    — POST /campaign/{campaignId}/upload-creative  (multipart)
  4. Attach    — POST /application/{appId}/draft/{draftId}/creative
  5. Publish   — POST /application/{appId}/draft/{draftId}/publish

Step 2b exists because an ad unit may already hold creative the client put
there. Anything already on the draft is left untouched so it is published
alongside the generated ad; our creative joins the same row so the ad unit
rotates between them rather than stacking them sequentially.

Banners: a new draft starts empty, so companion banners someone paired with
the live audio in Frequency's UI would be lost on every publish. Before
attaching, DAC reads the live (isCurrent) version from
GET /flight/application/{appId} and carries its banners onto the new audio.

Authentication: step 1 returns a `sid` session cookie. All subsequent requests
pass it explicitly via cookies= to avoid requests cookie-jar policy issues.
"""

import io
import logging
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from flask import current_app

from app.models.campaign import (
    FREQUENCY_TAG_APP_ID_KEY,
    FREQUENCY_TAG_BANNERS_KEY,
    FREQUENCY_TAG_TOKEN_KEY,
)

logger = logging.getLogger(__name__)

AUDIO_CREATIVE_TYPES = (None, "audio")
FLIGHT_VERSIONS_KEY = "versions"
VERSION_IS_CURRENT_KEY = "isCurrent"
VERSION_SOURCE_DRAFT_KEY = "application_draft_id"
CREATIVE_DATA_KEY = "data"
CREATIVE_BANNERS_KEY = "banners"
CREATIVE_ROW_INDEX_KEY = "rowIndex"
BANNER_SOURCE_TAG = "tag config"
BANNER_SOURCE_DRAFT = "existing row"
BANNER_SOURCE_LIVE = "live version"
BANNER_SOURCE_NONE = "none"


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


def deliver_ad(ad_run, tag: dict, final_ad_bytes: bytes) -> str:
    """Run the full five-step Frequency delivery workflow for one tag (ad unit)."""
    cfg = current_app.config
    base_url = cfg.get("CMPAPI_BASE_URL", "").rstrip("/")
    app_id = tag.get(FREQUENCY_TAG_APP_ID_KEY)

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
    token = tag.get(FREQUENCY_TAG_TOKEN_KEY)

    logger.info(
        "[Frequency] advertiser=%s  client=%s  token=%s",
        advertiser.name,
        client,
        "***" if token else None,
    )

    if not client:
        raise FrequencyNotConfiguredError(
            f"Advertiser '{advertiser.name}' has no Frequency client configured."
        )
    if not token:
        raise FrequencyNotConfiguredError(
            f"Campaign '{ad_run.campaign.name}' has no Frequency token configured."
        )

    # --- Step 1: Validate ---
    logger.info(
        "[Frequency] Step 1: validate — GET %s/campaign/validate/%s/<token>",
        base_url,
        client,
    )
    validate_resp = _validate(base_url, client, token)
    validate_data = validate_resp.json()
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
    draft_id = draft_data["id"]
    logger.info("[Frequency] Step 2 OK — draft_id=%s", draft_id)

    # --- Step 2b: See what creative the ad unit already carries ---
    logger.info(
        "[Frequency] Step 2b: existing creatives — GET %s/application/%s/draft/%s/creatives",
        base_url,
        app_id,
        draft_id,
    )
    existing_creatives = _get_draft_creatives(
        base_url, app_id, draft_id, auth_headers, auth_cookies
    )
    if existing_creatives:
        for existing in existing_creatives:
            logger.info(
                "[Frequency] Existing creative — name=%s  type=%s  rowIndex=%s  weight=%s  "
                "banners=%s",
                existing.get("audioFileName") or existing.get("fileName") or existing.get("name"),
                existing.get("type"),
                _row_of(existing),
                existing.get("fileWeight"),
                _banner_names(_creative_banners(existing)),
            )
        logger.info(
            "[Frequency] Step 2b OK — %d existing creative(s) will be published alongside "
            "the generated ad",
            len(existing_creatives),
        )
    else:
        logger.info("[Frequency] Step 2b OK — draft has no existing creatives")

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
    logger.info(
        "[Frequency] Step 3 OK — name=%s  url=%s",
        creative_data.get("name"),
        creative_data.get("url"),
    )

    # --- Step 4: Attach creative to draft ---
    row_index = _row_index_for_new_creative(existing_creatives)
    serve_option = _serve_option_for_new_creative(existing_creatives)
    banners, banners_source = _choose_banners(
        tag, existing_creatives, row_index, base_url, app_id, auth_headers, auth_cookies
    )
    logger.info(
        "[Frequency] Step 4: attach creative — POST %s/application/%s/draft/%s/creative  "
        "rowIndex=%s  serveOption=%s  banners=%s (source: %s)",
        base_url,
        app_id,
        draft_id,
        row_index,
        serve_option,
        _banner_names(banners),
        banners_source,
    )
    _attach_creative(
        base_url,
        app_id,
        draft_id,
        creative_data,
        auth_headers,
        auth_cookies,
        row_index=row_index,
        serve_option=serve_option,
        banners=banners,
    )
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
    logger.info("[Frequency] Delivery complete for ad_run #%s", ad_run.id)

    return vast_xml


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _validate(base_url: str, client: str, token: str) -> requests.Response:
    url = f"{base_url}/campaign/validate/{quote(client, safe='')}/{quote(token, safe='')}"
    resp = requests.get(url, timeout=30)
    logger.info("[Frequency] _validate HTTP %s", resp.status_code)
    _raise_for_status(resp, "validate")
    return resp


def _create_draft(base_url: str, app_id: str, headers: dict, cookies: dict) -> dict:
    url = f"{base_url}/application/{app_id}/draft"
    resp = requests.post(url, json={}, headers=headers, cookies=cookies, timeout=30)
    logger.info("[Frequency] _create_draft HTTP %s", resp.status_code)
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
    logger.info("[Frequency] _upload_creative HTTP %s", resp.status_code)
    _raise_for_status(resp, "upload creative")
    return resp.json()


def _get_draft_creatives(
    base_url: str, app_id: str, draft_id, headers: dict, cookies: dict
) -> list:
    """Return the creatives already attached to a draft.

    Never fatal: if the ad unit's existing creative can't be read we still
    publish the generated ad, we just can't report what it is sharing the
    unit with.
    """
    url = f"{base_url}/application/{app_id}/draft/{draft_id}/creatives"
    try:
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    except requests.RequestException as exc:
        logger.warning("[Frequency] _get_draft_creatives failed: %s", exc)
        return []

    logger.info("[Frequency] _get_draft_creatives HTTP %s", resp.status_code)
    if not resp.ok:
        logger.warning(
            "[Frequency] Could not read existing creatives: HTTP %s — %s",
            resp.status_code,
            resp.text[:300],
        )
        return []

    try:
        return _creative_list(resp.json())
    except ValueError:
        logger.warning("[Frequency] Existing creatives response was not JSON")
        return []


def _creative_list(payload) -> list:
    """Pull the creative array out of whichever envelope the API returned."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("creatives", "data", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            items = []
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _row_index_for_new_creative(existing_creatives: list) -> int:
    """Share a row with the existing audio creative so the unit rotates.

    Creatives in the same row rotate by weight; separate rows are separate
    slots. An ad unit that already holds audio should rotate the generated ad
    in with it, so we reuse the lowest audio row. With no audio to join, we
    must not default blindly to row 0 — a banner or other non-audio creative
    may already live there, and landing audio in the same row would collide
    with it instead of giving the audio its own slot. So we pick the lowest
    row index nothing else occupies.
    """
    audio_rows = [
        row
        for creative in existing_creatives
        if creative.get("type") in AUDIO_CREATIVE_TYPES
        for row in (_row_of(creative),)
        if row is not None
    ]
    if audio_rows:
        return min(audio_rows)

    used_rows = {
        row
        for creative in existing_creatives
        for row in (_row_of(creative),)
        if row is not None
    }
    candidate = 0
    while candidate in used_rows:
        candidate += 1
    return candidate


def _choose_banners(
    tag: dict, existing_creatives: list, row_index: int,
    base_url: str, app_id: str, headers: dict, cookies: dict,
) -> tuple[list, str]:
    """Pick the banners for the new audio, and say where they came from.

    Tag config wins, then the draft's own row, then the live version. The live
    version is only fetched when the cheaper sources come up empty.
    """
    tag_banners = tag.get(FREQUENCY_TAG_BANNERS_KEY)
    if tag_banners:
        return tag_banners, BANNER_SOURCE_TAG
    draft_banners = _banners_for_row(existing_creatives, row_index)
    if draft_banners:
        return draft_banners, BANNER_SOURCE_DRAFT
    live_creatives = _get_live_creatives(base_url, app_id, headers, cookies)
    live_banners = _banners_for_row(live_creatives, row_index)
    if live_banners:
        return live_banners, BANNER_SOURCE_LIVE
    return [], BANNER_SOURCE_NONE


def _banners_for_row(creatives: list, row_index: int) -> list:
    """Banners paired with the audio in the given row.

    The CMP API pairs a banner with a specific audio row via a `banners` field
    on the attach request — it is not a standing association on the ad unit.
    An attach that omits it starts the row with no banner, so joining a row
    means carrying its banners forward unchanged.
    """
    for creative in creatives:
        if creative.get("type") not in AUDIO_CREATIVE_TYPES:
            continue
        if _row_of(creative) != row_index:
            continue
        banners = _creative_banners(creative)
        if banners:
            return banners
    return []


def _creative_field(creative: dict, key: str):
    """Frequency stores row fields under `data`; the attach request sends them top level."""
    data = creative.get(CREATIVE_DATA_KEY)
    nested = data.get(key) if isinstance(data, dict) else None
    return nested if nested is not None else creative.get(key)


def _creative_banners(creative: dict) -> list:
    return _creative_field(creative, CREATIVE_BANNERS_KEY) or []


def _row_of(creative: dict):
    return _as_int(_creative_field(creative, CREATIVE_ROW_INDEX_KEY))


def _banner_names(banners: list) -> list:
    return [b.get("name") for b in banners if isinstance(b, dict)]


def _get_live_creatives(base_url: str, app_id: str, headers: dict, cookies: dict) -> list:
    """Creatives on the ad unit's live version. Never fatal.

    A published version keeps its creatives on the draft it was published
    from, so they are read through that draft.
    """
    draft_id = _live_source_draft_id(base_url, app_id, headers, cookies)
    if draft_id is None:
        logger.info("[Frequency] No live version found to carry banners from")
        return []
    logger.info("[Frequency] Live version was published from draft %s", draft_id)
    return _get_draft_creatives(base_url, app_id, draft_id, headers, cookies)


def _live_source_draft_id(base_url: str, app_id: str, headers: dict, cookies: dict):
    url = f"{base_url}/flight/application/{app_id}"
    try:
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    except requests.RequestException as exc:
        logger.warning("[Frequency] _live_source_draft_id failed: %s", exc)
        return None

    logger.info("[Frequency] _live_source_draft_id HTTP %s", resp.status_code)
    if not resp.ok:
        logger.warning(
            "[Frequency] Could not read flight: HTTP %s — %s", resp.status_code, resp.text[:300]
        )
        return None

    try:
        versions = resp.json().get(FLIGHT_VERSIONS_KEY) or []
    except (ValueError, AttributeError):
        logger.warning("[Frequency] Flight response was not a JSON object")
        return None
    return _current_version_draft_id(versions)


def _current_version_draft_id(versions: list):
    for version in versions:
        if isinstance(version, dict) and version.get(VERSION_IS_CURRENT_KEY):
            return version.get(VERSION_SOURCE_DRAFT_KEY)
    return None


def _serve_option_for_new_creative(existing_creatives: list) -> str:
    """Match the row's existing serve option so rotation stays consistent."""
    for creative in existing_creatives:
        option = creative.get("serveOption")
        if option in ("random", "sequential"):
            return option
    return "random"


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _attach_creative(
    base_url: str,
    app_id: str,
    draft_id,
    creative_data: dict,
    headers: dict,
    cookies: dict,
    row_index: int = 0,
    serve_option: str = "random",
    banners: list | None = None,
) -> None:
    url = f"{base_url}/application/{app_id}/draft/{draft_id}/creative"
    body = {
        "fileName": creative_data["name"],
        "fileUrl": creative_data["url"],
        "type": "audio",
        "serveOption": serve_option,
        "fileWeight": 100,
        "rowIndex": row_index,
    }
    if banners:
        body["banners"] = banners
    resp = requests.post(url, json=body, headers=headers, cookies=cookies, timeout=30)
    logger.info("[Frequency] _attach_creative HTTP %s", resp.status_code)
    _raise_for_status(resp, "attach creative")


def _publish_draft(
    base_url: str, app_id: str, draft_id, headers: dict, cookies: dict
) -> str:
    url = f"{base_url}/application/{app_id}/draft/{draft_id}/publish"
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    body = {"schedulePublishDate": today}
    resp = requests.post(url, json=body, headers=headers, cookies=cookies, timeout=30)
    logger.info("[Frequency] _publish_draft HTTP %s", resp.status_code)
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
    """Return the duration of the creative in whole seconds using ffprobe."""
    from app.push.audio import PushRejected, probe

    try:
        duration = int(probe(audio_bytes, "ad.mp3").duration)
    except PushRejected as exc:
        raise FrequencyDeliveryError(f"Could not determine audio duration: {exc}") from exc
    logger.info("[Frequency] Probed audio duration: %ds", duration)
    return duration
