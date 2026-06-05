"""World Cup feed — uses the /today proxy endpoint.

Calls the internal API proxy's /today route, which returns today's fixtures
(with goal scorers) and the current top-scorer table. No Claude extraction
needed — the response is already structured JSON.
"""

import logging
from datetime import datetime, timezone
import requests

from app.pipeline.exceptions import FeedFetchError
from app.pipeline.feeds.base import BaseFeed

logger = logging.getLogger(__name__)

# Soccer score-differential tiers for tone guidance
_SOCCER_TIERS = [
    {
        "max_diff": 1,
        "label": "close",
        "words": ["edged out", "squeaked past", "narrowly beat"],
    },
    {"max_diff": 2, "label": "comfortable", "words": ["beat", "defeated", "topped"]},
    {
        "max_diff": None,
        "label": "dominant",
        "words": ["crushed", "dominated", "routed"],
    },
]

DEFAULT_PROMPT_TEMPLATE = """\
You are writing a short radio ad script for the 2026 World Cup.

TODAY'S DATE: {match_date}

TODAY'S MATCHES:
{fixtures_formatted}

TOP SCORERS:
{top_scorers_formatted}

AD TAG (use this verbatim at the end):
{ad_tag}

{pronunciation_section}\
{tone_guidance}\
INSTRUCTIONS:
<<<<<<< Updated upstream
- The ad tag above is MANDATORY and must appear verbatim as the final words — do not change a single word
- Write World Cup coverage of STRICTLY NO MORE THAN {body_words} words, then append the ad tag exactly as written
- Total script must not exceed {target_words} words (= {target_seconds} seconds) — going over will cut the ad off on air
- Open with today's World Cup action — lead with the most exciting result or live match
- {fixture_mention_guidance}
- Write a smooth transition from the World Cup coverage into the ad tag
=======
- Write a natural, conversational script that fills but does NOT exceed {target_seconds} seconds when read aloud at a normal pace (hard maximum: {target_words} words)
- Open with today's World Cup action — lead with the most exciting result or live match
- {fixture_mention_guidance}
- Write a smooth transition from the football news to the advertiser
- Close with the advertiser name, tagline, and call to action
>>>>>>> Stashed changes
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if an enthusiastic local radio host is speaking
{pronunciation_instruction}\
- Output only the final script, nothing else\
"""


class WorldCupFeed(BaseFeed):
    """Fetches World Cup fixtures from the configured feed URL."""

    def fetch(self, campaign) -> dict:
        feed_url = campaign.feed_url
        if not feed_url:
            raise FeedFetchError("No feed URL configured for this campaign.")

        logger.info("Fetching World Cup data from %s...", feed_url)

        try:
            resp = requests.get(feed_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FeedFetchError(f"World Cup feed fetch failed: {exc}") from exc


        try:
            data = resp.json()
        except ValueError as exc:
            raise FeedFetchError(f"Invalid JSON from World Cup feed: {exc}") from exc

        fixtures = data.get("fixtures", [])
        top_scorers = data.get("top_scorers", [])
        match_date = data.get("date", datetime.now(timezone.utc).date().isoformat())

        if not fixtures and not top_scorers:
            raise FeedFetchError("No World Cup data for today.")

        return _build_template_vars(fixtures, top_scorers, match_date)

    def default_prompt_template(self) -> str:
        return DEFAULT_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_fixture(f: dict) -> str:
    home = f.get("home_team", "?")
    away = f.get("away_team", "?")
    status_short = f.get("status_short", "")
    home_goals = f.get("home_goals")
    away_goals = f.get("away_goals")
    round_ = f.get("round", "")
    elapsed = f.get("elapsed")

    if status_short == "FT":
        score = f"{away_goals}-{home_goals}"
        line = f"- {away} {score} {home} (FT"
        if f.get("penalty_home") is not None:
            line += f", pens {f['penalty_away']}-{f['penalty_home']}"
        elif f.get("extratime_home") is not None:
            line += ", AET"
        line += ")"
        scorers = _format_scorers(f.get("goal_scorers", []))
        if scorers:
            line += f"\n  Goals: {scorers}"
    elif status_short in ("1H", "2H", "HT", "ET", "BT", "P"):
        elapsed_str = f"{elapsed}'" if elapsed is not None else status_short
        hg = home_goals if home_goals is not None else 0
        ag = away_goals if away_goals is not None else 0
        line = f"- {away} {ag}-{hg} {home} (LIVE {elapsed_str})"
        scorers = _format_scorers(f.get("goal_scorers", []))
        if scorers:
            line += f"\n  Goals: {scorers}"
    else:
        date_str = f.get("date", "")
        try:
            ko = datetime.fromisoformat(date_str).astimezone(timezone.utc)
            time_str = ko.strftime("%H:%M UTC")
        except (ValueError, TypeError):
            time_str = "TBD"
        line = f"- {away} vs {home} ({time_str})"

    if round_:
        line += f" — {round_}"
    return line


def _format_scorers(goal_scorers: list[dict]) -> str:
    parts = []
    for g in goal_scorers:
        player = g.get("player", "?")
        minute = g.get("minute")
        team = g.get("team", "")
        detail = g.get("detail", "")
        entry = f"{player} ({team}"
        if minute is not None:
            entry += f" {minute}'"
        if detail and detail != "Normal Goal":
            entry += f", {detail}"
        entry += ")"
        parts.append(entry)
    return ", ".join(parts)


def _build_tone_guidance(fixtures: list[dict]) -> str:
    lines = []
    for f in fixtures:
        if f.get("status_short") != "FT":
            continue
        home_goals = f.get("home_goals")
        away_goals = f.get("away_goals")
        if home_goals is None or away_goals is None:
            continue

        h, a = int(home_goals), int(away_goals)
        diff = abs(h - a)
        home = f.get("home_team", "Home")
        away = f.get("away_team", "Away")

        if diff == 0:
            lines.append(
                f"- {home} vs {away} (draw): use language like "
                '"battled to a draw", "played to a stalemate", "shared the points"'
            )
            continue

        winner = home if h > a else away
        loser = away if winner == home else home

        tier = _SOCCER_TIERS[-1]
        for t in _SOCCER_TIERS:
            if t["max_diff"] is None or diff <= t["max_diff"]:
                tier = t
                break

        unit_label = f"{diff} goal{'s' if diff != 1 else ''}"
        word_suggestions = ", ".join(f'"{w}"' for w in tier["words"])
        lines.append(
            f"- {winner} beat {loser} ({unit_label} = {tier['label']} game): "
            f"use language like {word_suggestions}"
        )

    if not lines:
        return ""

    return "TONE GUIDANCE:\n" + "\n".join(lines) + "\n\n"


def _build_template_vars(
    fixtures: list[dict], top_scorers: list[dict], match_date: str
) -> dict:
    fixture_lines = [_format_fixture(f) for f in fixtures]
    fixtures_formatted = (
        "\n".join(fixture_lines) if fixture_lines else "No matches today."
    )

    scorer_lines = []
    for s in top_scorers[:5]:
        goals = s.get("goals", 0)
        assists = s.get("assists") or 0
        line = f"{s.get('rank', '')}. {s.get('player')} ({s.get('team')}) — {goals} goal{'s' if goals != 1 else ''}"
        if assists:
            line += f", {assists} assist{'s' if assists != 1 else ''}"
        scorer_lines.append(line)
    top_scorers_formatted = (
        "\n".join(scorer_lines) if scorer_lines else "No scorer data."
    )

    tone_guidance = _build_tone_guidance(fixtures)

    return {
        "match_date": match_date,
        "fixtures_formatted": fixtures_formatted,
        "top_scorers_formatted": top_scorers_formatted,
        "tone_guidance": tone_guidance,
        "num_fixtures": len(fixtures),
        "num_live": sum(
            1 for f in fixtures if f.get("status_short") in ("1H", "2H", "HT", "ET")
        ),
        "num_finished": sum(1 for f in fixtures if f.get("status_short") == "FT"),
    }
