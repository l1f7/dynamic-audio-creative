"""Concerts feed — JSON API or HTML scrape via Claude.

Adapted from the pilot's concerts.py. Now reads configuration from the
Campaign model instead of hardcoded constants.
"""

import json
import logging

import anthropic
import requests
from flask import current_app

from app.pipeline.exceptions import FeedFetchError
from app.pipeline.feeds.base import BaseFeed

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://gateway.admitone.com/embed/live-events?city=Vancouver"
DEFAULT_MAX_SHOWS = 3

DEFAULT_PROMPT_TEMPLATE = """\
You are writing a short radio ad script for a live music concert update.

PROMOTER / SPONSOR:
- Name: {advertiser_name}
- Description: {advertiser_description}
- Location: {target_city}
- Tagline: {advertiser_tagline}
- Call to action: {advertiser_cta}

UPCOMING SHOWS:
{upcoming_shows_formatted}

{pronunciation_section}\
INSTRUCTIONS:
- Write a natural, conversational script approximately {target_seconds} seconds long when read aloud (approximately {target_words} words)
- Open with energy — "Hey {target_city}, here's your concert update"
- Lead with the next upcoming show ({next_artist} on {next_date} at {next_venue})
- Tease 1-2 more shows from the lineup
- Close with the promoter name, tagline, and call to action
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if an enthusiastic local radio host is speaking
{pronunciation_instruction}\
- Output only the final script, nothing else\
"""

HTML_EXTRACTION_PROMPT = """\
Extract upcoming concert/event listings from the HTML below. Return ONLY a JSON \
array of objects, each with these keys: "artist", "date", "venue". \
Omit cancelled events. Sort by date ascending. Limit to the next {max_shows} \
upcoming shows.

If you cannot find any events, return an empty array: []

HTML:
{html_content}\
"""


class ConcertsFeed(BaseFeed):
    def fetch(self, campaign) -> dict:
        """Fetch concert data from a JSON API or HTML page."""
        config = campaign.feed_config or {}
        feed_url = campaign.feed_url or DEFAULT_FEED_URL
        venue_filter = config.get("venue_filter", "")
        max_shows = config.get("max_shows", DEFAULT_MAX_SHOWS)

        logger.info("Fetching concerts from %s...", feed_url)

        try:
            resp = requests.get(feed_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FeedFetchError(f"Feed fetch failed: {exc}") from exc

        content_type = resp.headers.get("content-type", "")

        if "json" in content_type or _looks_like_json(resp.text):
            shows = _parse_json_feed(resp.text, venue_filter)
        else:
            shows = self._extract_shows_from_html(resp.text, max_shows)

        if not shows:
            raise FeedFetchError("No items found in feed.")

        return _build_template_vars(shows[:max_shows])

    def default_prompt_template(self) -> str:
        return DEFAULT_PROMPT_TEMPLATE

    def _extract_shows_from_html(self, html: str, max_shows: int) -> list[dict]:
        logger.info("Page is HTML — extracting shows via Claude...")

        max_chars = 50_000
        if len(html) > max_chars:
            html = html[:max_chars]

        client = anthropic.Anthropic(
            api_key=current_app.config["ANTHROPIC_API_KEY"]
        )
        prompt = HTML_EXTRACTION_PROMPT.format(
            html_content=html, max_shows=max_shows
        )

        try:
            response = client.messages.create(
                model=current_app.config["CLAUDE_MODEL"],
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            logger.warning("Claude extraction failed: %s", exc)
            return []

        raw = response.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse Claude's extraction as JSON.")
            return []


# ---- helpers (shared with pilot) ----

def _looks_like_json(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_json_feed(text: str, venue_filter: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed: %s", exc)
        return []

    events = data if isinstance(data, list) else data.get("events", [])

    shows = []
    for e in events:
        if e.get("cancelled"):
            continue

        artist = e.get("artist") or e.get("title", "TBA")
        date = e.get("event_date") or e.get("date", "TBA")
        venue = e.get("venue", "")
        sold_out = e.get("sold_out", False)

        if venue_filter and venue.lower() != venue_filter.lower():
            continue

        show = {"artist": artist, "date": date, "venue": venue}
        if sold_out:
            show["note"] = "SOLD OUT"
        shows.append(show)

    return shows


def _build_template_vars(shows: list[dict]) -> dict:
    show_lines = []
    for s in shows:
        line = f"- {s['artist']} — {s['date']}"
        if s.get("venue"):
            line += f" at {s['venue']}"
        if s.get("note"):
            line += f" ({s['note']})"
        show_lines.append(line)

    first = shows[0] if shows else {"artist": "TBA", "date": "TBA", "venue": ""}

    return {
        "upcoming_shows_formatted": "\n".join(show_lines),
        "num_shows": len(shows),
        "next_artist": first["artist"],
        "next_date": first["date"],
        "next_venue": first.get("venue", ""),
    }
