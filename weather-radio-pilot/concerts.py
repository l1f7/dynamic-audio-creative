"""Fetch concert data from a live feed or HTML page.

Supports three modes (auto-detected from the response):
  1. JSON API — structured event data (e.g. AdmitOne gateway)
  2. HTML page — raw markup sent to Claude for extraction
  3. Hardcoded fallback — if no CONCERTS_FEED_URL is configured

Configure via environment variables:
  CONCERTS_FEED_URL  — URL to fetch (JSON API or HTML page)
  CONCERTS_VENUE     — (optional) filter events to a specific venue name
"""

import json
import os
import sys

import anthropic
import requests

from config import CLAUDE_MODEL

# ---- Sponsor / venue config ----

VENUE = {
    "venue_name": "MRG Live",
    "venue_location": "Vancouver, BC",
    "venue_tagline": "Bringing you positive shareable experiences",
    "venue_cta": "Get tickets at mrglive.com",
}

# Pronunciation guide — maps written form to how it should appear in the
# script so TTS reads it correctly. Included in the Claude prompt.
PRONUNCIATION_GUIDE = {
    "MRG": "M-R-G",
    "mrglive.com": "M-R-G Live dot com",
}

# Default feed — MRG Live Vancouver via AdmitOne API
DEFAULT_FEED_URL = "https://gateway.admitone.com/embed/live-events?city=Vancouver"

# How many upcoming shows to include in the ad script
MAX_SHOWS = 3

# Hardcoded fallback (used only if no feed URL is set and the default fails)
FALLBACK_SHOWS = [
    {"artist": "Chet Faker", "date": "May 8th, 2026", "venue": "Vogue Theatre"},
    {"artist": "Snail Mail", "date": "May 9th, 2026", "venue": "Vogue Theatre"},
    {"artist": "Good Kid", "date": "May 10th, 2026", "venue": "Vogue Theatre"},
]

# ---- Prompt template ----

CONCERT_PROMPT_TEMPLATE = """\
You are writing a short radio ad script for a live music concert update.

PROMOTER / SPONSOR:
- Name: {venue_name}
- Location: {venue_location}
- Tagline: {venue_tagline}
- Call to action: {venue_cta}

UPCOMING SHOWS:
{upcoming_shows_formatted}

PRONUNCIATION (use these exact spellings so text-to-speech reads them correctly):
{pronunciation_guide_formatted}

INSTRUCTIONS:
- Write a natural, conversational script approximately {target_seconds} seconds long when read aloud (approximately {target_words} words)
- Open with energy — "Hey Vancouver, here's your concert update"
- Lead with the next upcoming show ({next_artist} on {next_date} at {next_venue})
- Tease 1-2 more shows from the lineup
- Close with the promoter name, tagline, and call to action
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if an enthusiastic local radio host is speaking
- Use the pronunciation spellings above whenever those words appear
- Output only the final script, nothing else

NOTE: This is a test script for prototype purposes only.\
"""

# ---- Claude prompt for extracting shows from raw HTML ----

HTML_EXTRACTION_PROMPT = """\
Extract upcoming concert/event listings from the HTML below. Return ONLY a JSON array \
of objects, each with these keys: "artist", "date", "venue". \
Omit cancelled events. Sort by date ascending. Limit to the next {max_shows} upcoming shows.

If you cannot find any events, return an empty array: []

HTML:
{html_content}\
"""


# ---- Data fetching ----

def fetch_concerts() -> dict:
    """Fetch upcoming concert data and return a dict for prompt interpolation.

    Auto-detects whether the feed is JSON or HTML:
      - JSON: parse events directly
      - HTML: send to Claude for structured extraction
      - Failure: fall back to hardcoded show data
    """
    feed_url = os.environ.get("CONCERTS_FEED_URL", DEFAULT_FEED_URL)
    venue_filter = os.environ.get("CONCERTS_VENUE", "")

    print(f"Fetching concerts from {feed_url}...")

    try:
        resp = requests.get(feed_url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  WARNING: Feed fetch failed ({exc}), using fallback data.")
        shows = FALLBACK_SHOWS[:MAX_SHOWS]
        return _build_template_vars(shows)

    content_type = resp.headers.get("content-type", "")

    # --- JSON feed (e.g. AdmitOne API) ---
    if "json" in content_type or _looks_like_json(resp.text):
        shows = _parse_json_feed(resp.text, venue_filter)
    # --- HTML page ---
    else:
        shows = _extract_shows_from_html(resp.text)

    if not shows:
        print("  WARNING: No shows found in feed, using fallback data.")
        shows = FALLBACK_SHOWS[:MAX_SHOWS]

    return _build_template_vars(shows[:MAX_SHOWS])


def _looks_like_json(text: str) -> bool:
    """Quick sniff — does the response body start with JSON-ish characters?"""
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_json_feed(text: str, venue_filter: str) -> list[dict]:
    """Parse a JSON events feed (AdmitOne format or plain array)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"  WARNING: JSON parse failed: {exc}")
        return []

    # Handle AdmitOne wrapper: {"events": [...]}
    events = data if isinstance(data, list) else data.get("events", [])

    shows = []
    for e in events:
        # Skip cancelled or sold-out events
        if e.get("cancelled"):
            continue

        artist = e.get("artist") or e.get("title", "TBA")
        date = e.get("event_date") or e.get("date", "TBA")
        venue = e.get("venue", "")
        sold_out = e.get("sold_out", False)

        # Optional venue filter
        if venue_filter and venue.lower() != venue_filter.lower():
            continue

        show = {"artist": artist, "date": date, "venue": venue}
        if sold_out:
            show["note"] = "SOLD OUT"
        shows.append(show)

    return shows


def _extract_shows_from_html(html: str) -> list[dict]:
    """Send raw HTML to Claude and ask it to extract structured show data."""
    print("  Page is HTML — extracting shows via Claude...")

    # Truncate very large pages to stay within token limits
    max_chars = 50_000
    if len(html) > max_chars:
        html = html[:max_chars]

    client = anthropic.Anthropic()
    prompt = HTML_EXTRACTION_PROMPT.format(html_content=html, max_shows=MAX_SHOWS)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        print(f"  WARNING: Claude extraction failed: {exc}")
        return []

    raw = response.content[0].text.strip()

    # Claude may wrap JSON in ```json ... ``` fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        shows = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  WARNING: Could not parse Claude's extraction as JSON.")
        return []

    return shows


# ---- Template rendering ----

def _build_template_vars(shows: list[dict]) -> dict:
    """Build the template variable dict from a list of show dicts."""
    show_lines = []
    for s in shows:
        line = f"- {s['artist']} — {s['date']}"
        if s.get("venue"):
            line += f" at {s['venue']}"
        if s.get("note"):
            line += f" ({s['note']})"
        show_lines.append(line)

    first = shows[0] if shows else {"artist": "TBA", "date": "TBA", "venue": ""}

    # Format pronunciation guide for the prompt
    guide_lines = [f'- "{k}" → write as "{v}"' for k, v in PRONUNCIATION_GUIDE.items()]
    pronunciation_formatted = "\n".join(guide_lines) if guide_lines else "- (none)"

    data = {
        **VENUE,
        "upcoming_shows_formatted": "\n".join(show_lines),
        "pronunciation_guide_formatted": pronunciation_formatted,
        "num_shows": len(shows),
        "next_artist": first["artist"],
        "next_date": first["date"],
        "next_venue": first.get("venue", ""),
    }

    print(f"Concert update for {VENUE['venue_name']} ({VENUE['venue_location']})")
    for line in show_lines:
        print(f"  {line}")

    return data
