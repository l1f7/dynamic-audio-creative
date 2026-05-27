"""Generic feed — uses Claude to extract structured data from any URL.

Handles JSON APIs, HTML pages, and XML feeds by sending the raw content
to Claude for intelligent extraction based on the campaign's feed_type.
Includes sport-specific tone guidance based on score differentials.
"""

import json
import logging

import anthropic
import requests
from flask import current_app

from app.pipeline.exceptions import FeedFetchError
from app.pipeline.feeds.base import BaseFeed

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 5

# ---------------------------------------------------------------------------
# Sport-specific score differential thresholds
#
# What counts as a "close game" vs. a "blowout" varies drastically by sport.
# A 3-goal differential in soccer is a rout; in basketball it's a nail-biter.
# ---------------------------------------------------------------------------
SPORT_THRESHOLDS = {
    "soccer": {
        "unit": "goal",
        "tiers": [
            {"max_diff": 1, "label": "close", "words": ["edged out", "squeaked past", "narrowly beat"]},
            {"max_diff": 2, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "dominated", "routed"]},
        ],
    },
    "basketball": {
        "unit": "point",
        "tiers": [
            {"max_diff": 5, "label": "close", "words": ["edged out", "squeaked past", "narrowly beat"]},
            {"max_diff": 15, "label": "comfortable", "words": ["beat", "defeated", "handled"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "blew out", "dominated"]},
        ],
    },
    "football": {
        "unit": "point",
        "tiers": [
            {"max_diff": 7, "label": "close", "words": ["edged out", "held off", "narrowly beat"]},
            {"max_diff": 17, "label": "comfortable", "words": ["beat", "defeated", "handled"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "blew out", "dominated"]},
        ],
    },
    "hockey": {
        "unit": "goal",
        "tiers": [
            {"max_diff": 1, "label": "close", "words": ["edged out", "squeaked past", "narrowly beat"]},
            {"max_diff": 2, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "dominated", "routed"]},
        ],
    },
    "baseball": {
        "unit": "run",
        "tiers": [
            {"max_diff": 2, "label": "close", "words": ["edged out", "squeaked past", "narrowly beat"]},
            {"max_diff": 5, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "blew out", "routed"]},
        ],
    },
    "rugby": {
        "unit": "point",
        "tiers": [
            {"max_diff": 7, "label": "close", "words": ["edged out", "held off", "narrowly beat"]},
            {"max_diff": 20, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "dominated", "routed"]},
        ],
    },
    "cricket": {
        "unit": "run",
        "tiers": [
            {"max_diff": 20, "label": "close", "words": ["edged out", "squeaked past", "narrowly beat"]},
            {"max_diff": 80, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
            {"max_diff": None, "label": "dominant", "words": ["crushed", "dominated", "routed"]},
        ],
    },
}

# Map common league/competition names to sport types
LEAGUE_TO_SPORT = {
    "nfl": "football",
    "cfl": "football",
    "nba": "basketball",
    "wnba": "basketball",
    "ncaa basketball": "basketball",
    "nhl": "hockey",
    "mlb": "baseball",
    "mls": "soccer",
    "epl": "soccer",
    "premier league": "soccer",
    "la liga": "soccer",
    "bundesliga": "soccer",
    "serie a": "soccer",
    "ligue 1": "soccer",
    "champions league": "soccer",
    "world cup": "soccer",
    "liga mx": "soccer",
    "nrl": "rugby",
    "super rugby": "rugby",
    "six nations": "rugby",
    "ipl": "cricket",
}

# ---------------------------------------------------------------------------
# Claude extraction prompt — adapts to any feed type
# ---------------------------------------------------------------------------
EXTRACTION_PROMPT = """\
Extract structured data from the content below. The feed type is "{feed_type}".

Return ONLY a JSON array of objects. Choose keys appropriate for the content:

For sports feeds, use these keys:
"home_team", "away_team", "home_score", "away_score", "date", "venue", \
"status" (e.g. "final", "upcoming", "in_progress").
Only include score fields for completed or in-progress games.

For event/listing feeds, use: "title", "date", "venue", "description".

For news feeds, use: "headline", "summary", "date", "source".

If the content doesn't clearly match any of these, use the most appropriate \
keys to capture the important information.

Sort by date ascending. Limit to {max_items} items. Omit cancelled items.
If you cannot find any relevant items, return an empty array: []

CONTENT:
{content}\
"""

# ---------------------------------------------------------------------------
# Default prompt template — works for any feed type
# ---------------------------------------------------------------------------
DEFAULT_PROMPT_TEMPLATE = """\
You are writing a short radio ad script.

CONTENT TYPE: {feed_type}

DATA:
{items_formatted}

{tone_guidance}\
ADVERTISER:
- Name: {advertiser_name}
- Description: {advertiser_description}
- Location: {target_city}
- Tagline: {advertiser_tagline}
- Call to action: {advertiser_cta}

{pronunciation_section}\
INSTRUCTIONS:
- Write a natural, conversational script approximately {target_seconds} seconds \
long when read aloud (approximately {target_words} words)
- Lead with the most interesting or timely item from the data
- Weave in 1-2 more items if time allows
- Close with the advertiser name, tagline, and call to action
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if a friendly, knowledgeable local radio host is speaking
{pronunciation_instruction}\
- Output only the final script, nothing else\
"""


class GenericFeed(BaseFeed):
    """Feed that uses Claude to extract structured data from any URL.

    Works with JSON APIs, HTML pages, and XML feeds. The campaign's
    feed_type guides Claude on what kind of data to extract. For sports
    feeds, score differentials are analysed to provide sport-appropriate
    tone guidance (e.g. a 3-goal soccer win is described as dominant,
    while a 3-point basketball win is described as close).
    """

    def fetch(self, campaign) -> dict:
        """Fetch and extract data from any feed URL."""
        config = campaign.feed_config or {}
        feed_url = campaign.feed_url
        feed_type = campaign.feed_type or "general"
        max_items = config.get("max_items", DEFAULT_MAX_ITEMS)

        if not feed_url:
            raise FeedFetchError("No feed URL configured for this campaign.")

        logger.info("Fetching %s feed from %s...", feed_type, feed_url)

        try:
            resp = requests.get(feed_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FeedFetchError(f"Feed fetch failed: {exc}") from exc

        items = self._extract_items(resp.text, feed_type, max_items)

        if not items:
            raise FeedFetchError("No items found in feed.")

        items = items[:max_items]

        sport = _detect_sport(feed_type)
        tone_guidance = _build_tone_guidance(items, sport) if sport else ""

        return _build_template_vars(items, feed_type, tone_guidance)

    def default_prompt_template(self) -> str:
        return DEFAULT_PROMPT_TEMPLATE

    def _extract_items(
        self, content: str, feed_type: str, max_items: int
    ) -> list[dict]:
        """Use Claude to extract structured items from raw feed content."""
        logger.info("Extracting %s items via Claude...", feed_type)

        max_chars = 50_000
        if len(content) > max_chars:
            content = content[:max_chars]

        client = anthropic.Anthropic(
            api_key=current_app.config["ANTHROPIC_API_KEY"]
        )
        prompt = EXTRACTION_PROMPT.format(
            feed_type=feed_type,
            max_items=max_items,
            content=content,
        )

        try:
            response = client.messages.create(
                model=current_app.config["CLAUDE_MODEL"],
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            logger.warning("Claude extraction failed: %s", exc)
            return []

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse Claude's extraction as JSON.")
            return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_sport(feed_type: str) -> str | None:
    """Detect the specific sport from a feed_type string.

    Handles direct sport names ("soccer"), league names ("nfl"),
    and compound strings ("nba scores", "premier league results").
    """
    ft = feed_type.lower().strip()

    # Direct match
    if ft in SPORT_THRESHOLDS:
        return ft

    # League name — exact match
    if ft in LEAGUE_TO_SPORT:
        return LEAGUE_TO_SPORT[ft]

    # Substring match (e.g. "soccer scores", "nba results")
    for league, sport in LEAGUE_TO_SPORT.items():
        if league in ft:
            return sport
    for sport in SPORT_THRESHOLDS:
        if sport in ft:
            return sport

    # "sports" alone isn't specific enough to pick thresholds
    return None


def _build_tone_guidance(items: list[dict], sport: str) -> str:
    """Build tone/word-choice guidance based on sport-specific score differentials.

    Examines each game's score differential and maps it to the appropriate
    tier for the detected sport, producing per-game word suggestions that
    the script-writing prompt can use.
    """
    thresholds = SPORT_THRESHOLDS.get(sport)
    if not thresholds:
        return ""

    guidance_lines = []
    for item in items:
        home_score = item.get("home_score")
        away_score = item.get("away_score")
        if home_score is None or away_score is None:
            continue

        try:
            h = int(home_score)
            a = int(away_score)
        except (ValueError, TypeError):
            continue

        diff = abs(h - a)

        if diff == 0:
            # Draw / tie
            home = item.get("home_team", "Home")
            away = item.get("away_team", "Away")
            guidance_lines.append(
                f"- {home} vs {away} (draw): use language like "
                f'"battled to a draw", "played to a stalemate", "shared the points"'
            )
            continue

        home = item.get("home_team", "Home")
        away = item.get("away_team", "Away")
        winner = home if h > a else away
        loser = away if winner == home else home

        # Find the matching tier
        tier = thresholds["tiers"][-1]  # fallback to highest tier
        for t in thresholds["tiers"]:
            if t["max_diff"] is None or diff <= t["max_diff"]:
                tier = t
                break

        unit = thresholds["unit"]
        unit_label = f"{diff} {unit}{'s' if diff != 1 else ''}"
        word_suggestions = ", ".join(f'"{w}"' for w in tier["words"])

        guidance_lines.append(
            f"- {winner} vs {loser} ({unit_label} differential = "
            f"{tier['label']} game): use language like {word_suggestions}"
        )

    if not guidance_lines:
        return ""

    return (
        f"TONE GUIDANCE ({sport.upper()} — word choices based on score "
        f"differential):\n"
        + "\n".join(guidance_lines)
        + "\n\n"
    )


def _build_template_vars(
    items: list[dict], feed_type: str, tone_guidance: str
) -> dict:
    """Build template variables from extracted items."""
    item_lines = []
    for item in items:
        # Sports format
        if "home_team" in item and "away_team" in item:
            line = f"- {item['away_team']} at {item['home_team']}"
            if (
                item.get("away_score") is not None
                and item.get("home_score") is not None
            ):
                line += f" — {item['away_score']}-{item['home_score']}"
            if item.get("date"):
                line += f" ({item['date']})"
            if item.get("status"):
                line += f" [{item['status']}]"
        # Event format
        elif "title" in item:
            line = f"- {item['title']}"
            if item.get("date"):
                line += f" — {item['date']}"
            if item.get("venue"):
                line += f" at {item['venue']}"
            if item.get("description"):
                line += f": {item['description']}"
        # News format
        elif "headline" in item:
            line = f"- {item['headline']}"
            if item.get("date"):
                line += f" ({item['date']})"
            if item.get("summary"):
                line += f": {item['summary']}"
        # Fallback — just dump key-value pairs
        else:
            parts = [f"{k}: {v}" for k, v in item.items() if v]
            line = f"- {', '.join(parts)}"

        item_lines.append(line)

    return {
        "items_formatted": "\n".join(item_lines),
        "num_items": len(items),
        "feed_type": feed_type,
        "tone_guidance": tone_guidance,
    }
