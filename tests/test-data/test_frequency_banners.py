#!/usr/bin/env python3
"""Standalone probe: does Frequency's attach-creative endpoint actually honor `banners`?

Mirrors the real steps in app/delivery/frequency.py (validate -> create draft ->
upload audio -> attach) but stops after attach and reads the draft back, rather
than publishing. No Flask app or database needed -- fill in the constants below
with real values for the CTN Drop Test campaign and run:

    python3 test_frequency_banners.py --audio path/to/test.mp3

If ffprobe isn't on PATH, pass --duration <seconds> instead.

Cleanup: this leaves one extra draft on the CTN Drop Test app (visible in
Frequency's UI as another "Version N Copy", same as clicking Duplicate does).
Delete it yourself once you're done inspecting, or leave it -- it is not live
until published.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Fill these in with real values -----------------------------------------
BASE_URL = "https://cmp.frequencyads.com"
CLIENT = "FILL_ME_IN"        # advertiser.frequency_client, e.g. maybe "westernmed"
                              # (a guess based on the executionArn strings we saw
                              # -- "westernmed-25544-2148197-..." -- confirm it)
TOKEN = "FILL_ME_IN"          # the CTN Drop Test campaign's Frequency tag token
APP_ID = "2148197"            # CTN Drop Test app id, already confirmed
# -----------------------------------------------------------------------------

TEST_BANNER = {
    "name": "DAC Test Banner",
    "width": 300,
    "height": 250,
    "clickOut": "https://example.com",
    "altText": "DAC test banner",
    "fileUrl": "https://placehold.co/300x250.png?text=DAC+Test+Banner",
}


def probe_duration(path: Path) -> int:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return int(round(float(json.loads(out.stdout)["format"]["duration"])))
    except FileNotFoundError:
        pass  # no ffprobe on PATH -- fall back to parsing ffmpeg's stderr below
    except (subprocess.CalledProcessError, KeyError, ValueError) as exc:
        raise SystemExit(
            f"Could not probe duration with ffprobe ({exc}). Pass --duration <seconds> instead."
        )

    try:
        out = subprocess.run(
            ["ffmpeg", "-i", str(path)], capture_output=True, text=True, timeout=30,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out.stderr)
        if not match:
            raise ValueError("no Duration line in ffmpeg output")
        hours, minutes, seconds = match.groups()
        return int(round(int(hours) * 3600 + int(minutes) * 60 + float(seconds)))
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(
            f"Could not probe duration with ffprobe or ffmpeg ({exc}). Pass --duration <seconds> instead."
        )


def step(label: str):
    print(f"\n--- {label} ---")


def die_on_error(resp: requests.Response, step_name: str):
    if not resp.ok:
        print(f"FAILED at {step_name}: HTTP {resp.status_code}")
        print(resp.text[:1000])
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="Path to a small test MP3")
    parser.add_argument("--duration", type=int, help="Override duration in seconds (skip ffprobe)")
    args = parser.parse_args()

    if CLIENT == "FILL_ME_IN" or TOKEN == "FILL_ME_IN":
        raise SystemExit("Fill in CLIENT and TOKEN at the top of this script first.")

    audio_path = Path(args.audio)
    audio_bytes = audio_path.read_bytes()
    duration = args.duration or probe_duration(audio_path)
    print(f"Audio: {audio_path.name} ({len(audio_bytes)} bytes, {duration}s)")

    # --- Step 1: validate ---
    step("Step 1: validate")
    resp = requests.get(f"{BASE_URL}/campaign/validate/{CLIENT}/{TOKEN}", timeout=30)
    die_on_error(resp, "validate")
    data = resp.json()
    campaign_id = data["tokenData"]["campaign_id"]
    auth_token = data.get("authToken")
    if not auth_token:
        raise SystemExit(f"No authToken in validate response: {data}")
    print(f"campaign_id={campaign_id}  authToken=received")
    headers = {"Authorization": f"Bearer {auth_token}"}

    # --- Step 1b: can our partner authToken read /application/{appId} at all? ---
    # This is the endpoint that returned versions[].isCurrent when called with
    # your logged-in browser session (sid cookie + user JWT). We've never
    # confirmed the partner-scoped authToken from validate() has the same
    # access. Purely a GET -- read-only, safe either way.
    step("Step 1b: can the partner authToken read GET /application/{appId}?")
    resp = requests.get(f"{BASE_URL}/application/{APP_ID}", headers=headers, timeout=30)
    print(f"HTTP {resp.status_code}")
    if resp.ok:
        try:
            app_data = resp.json()
            current = next((v for v in app_data.get("versions", []) if v.get("isCurrent")), None)
            print("SUCCESS -- the partner authToken CAN read this endpoint.")
            print(f"Current live version: id={current.get('id') if current else None}  "
                  f"version={current.get('version') if current else None}")
        except ValueError:
            print("200 OK but response wasn't JSON:")
            print(resp.text[:1000])
    else:
        print("REJECTED -- the partner authToken cannot read this endpoint as-is:")
        print(resp.text[:500])

    # --- Step 2: create draft (empty, same as DAC does today) ---
    step("Step 2: create draft")
    resp = requests.post(f"{BASE_URL}/application/{APP_ID}/draft", json={}, headers=headers, timeout=30)
    die_on_error(resp, "create draft")
    draft_id = resp.json()["id"]
    print(f"draft_id={draft_id}")

    # --- Step 2b: what's already on this draft? ---
    step("Step 2b: existing creatives on the new draft")
    resp = requests.get(
        f"{BASE_URL}/application/{APP_ID}/draft/{draft_id}/creatives", headers=headers, timeout=30
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text[:2000])

    # --- Step 3: upload test audio ---
    step("Step 3: upload creative")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"banner_test_{ts}.mp3"
    files = {"file": (filename, audio_bytes, "audio/mpeg")}
    form = {"duration": str(duration), "applicationId": str(APP_ID)}
    resp = requests.post(
        f"{BASE_URL}/campaign/{campaign_id}/upload-creative",
        files=files, data=form, headers=headers, timeout=120,
    )
    die_on_error(resp, "upload creative")
    creative_data = resp.json()
    print(f"uploaded: name={creative_data.get('name')}  url={creative_data.get('url')}")

    # --- Step 4: attach WITH banners ---
    step("Step 4: attach creative (with banners)")
    body = {
        "fileName": creative_data["name"],
        "fileUrl": creative_data["url"],
        "type": "audio",
        "serveOption": "random",
        "fileWeight": 100,
        "rowIndex": 0,
        "banners": [TEST_BANNER],
    }
    print("Request body:")
    print(json.dumps(body, indent=2))
    resp = requests.post(
        f"{BASE_URL}/application/{APP_ID}/draft/{draft_id}/creative",
        json=body, headers=headers, timeout=30,
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text[:2000])
    if not resp.ok:
        print("\n=> Attach REJECTED the request outright. That's a clear 'no' on `banners`"
              " as sent -- check the response body above for why (bad field name/shape?).")
        sys.exit(1)

    # --- Read back: did the banner survive? ---
    step("Read back: GET draft creatives again")
    resp = requests.get(
        f"{BASE_URL}/application/{APP_ID}/draft/{draft_id}/creatives", headers=headers, timeout=30
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text[:4000])

    print(
        f"\n=== Draft {draft_id} created on app {APP_ID}, NOT published. ===\n"
        f"Open Frequency's editor for app {APP_ID} (the 'adops'/external-builder page), find\n"
        f"the newest draft, and check visually whether 'DAC Test Banner' shows attached to\n"
        f"the new audio row. The JSON above tells us whether the API *echoed back* what we\n"
        f"sent -- Frequency's own UI is the real ground truth for whether it actually took.\n"
        f"Delete the draft afterward if you don't want it cluttering the app's draft list."
    )


if __name__ == "__main__":
    main()
