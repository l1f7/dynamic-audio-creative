"""World Cup score proxy — wraps api-football.com endpoints.

Routes (all under /api/v1/):
  GET /standings   — group standings
  GET /scores      — all fixtures with scores
  GET /live        — currently live matches
  GET /today       — today's fixtures + top scorers
  GET /yesterday   — completed fixtures from the previous 24 hours
  GET /update      — live + recent scores + standings + top scorers

Add ?testing=true to any route to get fake data without hitting the API.
Requires API_FOOTBALL_KEY environment variable.
"""

import os
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, request

from flask import current_app

from app.api import api_bp


def _check_secret():
    expected = current_app.config.get("SCOREPROXY_SECRET")
    if expected and request.args.get("secret") != expected:
        return jsonify({"error": "Unauthorized"}), 401
    return None

API_KEY = os.environ.get("API_FOOTBALL_KEY")
API_BASE = "https://v3.football.api-sports.io"
LEAGUE_ID = 1
SEASON = 2026

HEADERS = {"x-apisports-key": API_KEY}


# ---------------------------------------------------------------------------
# Fake data for ?testing=true
# ---------------------------------------------------------------------------

FAKE_STANDINGS = [
    {"group": "Group A", "position": 1, "team_id": 2, "team": "USA", "logo": "https://media.api-sports.io/football/teams/2.png", "played": 2, "win": 2, "draw": 0, "lose": 0, "goals_for": 5, "goals_against": 1, "goal_diff": 4, "points": 6, "form": "WW"},
    {"group": "Group A", "position": 2, "team_id": 10, "team": "Mexico", "logo": "https://media.api-sports.io/football/teams/10.png", "played": 2, "win": 1, "draw": 0, "lose": 1, "goals_for": 3, "goals_against": 3, "goal_diff": 0, "points": 3, "form": "WL"},
    {"group": "Group A", "position": 3, "team_id": 96, "team": "Honduras", "logo": "https://media.api-sports.io/football/teams/96.png", "played": 2, "win": 0, "draw": 1, "lose": 1, "goals_for": 2, "goals_against": 4, "goal_diff": -2, "points": 1, "form": "DL"},
    {"group": "Group A", "position": 4, "team_id": 26, "team": "Cameroon", "logo": "https://media.api-sports.io/football/teams/26.png", "played": 2, "win": 0, "draw": 1, "lose": 1, "goals_for": 1, "goals_against": 3, "goal_diff": -2, "points": 1, "form": "DL"},
    {"group": "Group B", "position": 1, "team_id": 6, "team": "Brazil", "logo": "https://media.api-sports.io/football/teams/6.png", "played": 2, "win": 1, "draw": 1, "lose": 0, "goals_for": 4, "goals_against": 2, "goal_diff": 2, "points": 4, "form": "WD"},
    {"group": "Group B", "position": 2, "team_id": 7, "team": "Argentina", "logo": "https://media.api-sports.io/football/teams/7.png", "played": 2, "win": 1, "draw": 1, "lose": 0, "goals_for": 3, "goals_against": 1, "goal_diff": 2, "points": 4, "form": "DW"},
    {"group": "Group B", "position": 3, "team_id": 30, "team": "Colombia", "logo": "https://media.api-sports.io/football/teams/30.png", "played": 2, "win": 0, "draw": 1, "lose": 1, "goals_for": 2, "goals_against": 3, "goal_diff": -1, "points": 1, "form": "DL"},
    {"group": "Group B", "position": 4, "team_id": 31, "team": "Ecuador", "logo": "https://media.api-sports.io/football/teams/31.png", "played": 2, "win": 0, "draw": 1, "lose": 1, "goals_for": 1, "goals_against": 4, "goal_diff": -3, "points": 1, "form": "LD"},
    {"group": "Group C", "position": 1, "team_id": 25, "team": "Germany", "logo": "https://media.api-sports.io/football/teams/25.png", "played": 2, "win": 2, "draw": 0, "lose": 0, "goals_for": 6, "goals_against": 2, "goal_diff": 4, "points": 6, "form": "WW"},
    {"group": "Group C", "position": 2, "team_id": 2, "team": "France", "logo": "https://media.api-sports.io/football/teams/2.png", "played": 2, "win": 1, "draw": 0, "lose": 1, "goals_for": 3, "goals_against": 3, "goal_diff": 0, "points": 3, "form": "WL"},
    {"group": "Group C", "position": 3, "team_id": 9, "team": "Spain", "logo": "https://media.api-sports.io/football/teams/9.png", "played": 2, "win": 1, "draw": 0, "lose": 1, "goals_for": 2, "goals_against": 3, "goal_diff": -1, "points": 3, "form": "LW"},
    {"group": "Group C", "position": 4, "team_id": 27, "team": "Portugal", "logo": "https://media.api-sports.io/football/teams/27.png", "played": 2, "win": 0, "draw": 0, "lose": 2, "goals_for": 1, "goals_against": 4, "goal_diff": -3, "points": 0, "form": "LL"},
]

FAKE_FIXTURES = [
    {"fixture_id": 1001, "date": "2026-06-11T18:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "SoFi Stadium", "home_team": "USA", "home_team_id": 2, "away_team": "Honduras", "away_team_id": 96, "home_goals": 3, "away_goals": 1, "halftime_home": 1, "halftime_away": 0, "fulltime_home": 3, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 14, "team": "USA", "player": "Christian Pulisic", "assist": "Tyler Adams", "detail": "Normal Goal"},
        {"minute": 38, "team": "Honduras", "player": "Alberth Elis", "assist": None, "detail": "Normal Goal"},
        {"minute": 61, "team": "USA", "player": "Folarin Balogun", "assist": "Christian Pulisic", "detail": "Normal Goal"},
        {"minute": 78, "team": "USA", "player": "Weston McKennie", "assist": None, "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1002, "date": "2026-06-11T21:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "Estadio Azteca", "home_team": "Mexico", "home_team_id": 10, "away_team": "Cameroon", "away_team_id": 26, "home_goals": 2, "away_goals": 1, "halftime_home": 1, "halftime_away": 1, "fulltime_home": 2, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 22, "team": "Mexico", "player": "Hirving Lozano", "assist": None, "detail": "Normal Goal"},
        {"minute": 44, "team": "Cameroon", "player": "Vincent Aboubakar", "assist": None, "detail": "Normal Goal"},
        {"minute": 71, "team": "Mexico", "player": "Raúl Jiménez", "assist": "Hirving Lozano", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1003, "date": "2026-06-15T18:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 2", "venue": "SoFi Stadium", "home_team": "USA", "home_team_id": 2, "away_team": "Cameroon", "away_team_id": 26, "home_goals": 2, "away_goals": 0, "halftime_home": 1, "halftime_away": 0, "fulltime_home": 2, "fulltime_away": 0, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 31, "team": "USA", "player": "Christian Pulisic", "assist": None, "detail": "Penalty"},
        {"minute": 83, "team": "USA", "player": "Folarin Balogun", "assist": "Weston McKennie", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1004, "date": "2026-06-15T21:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 2", "venue": "AT&T Stadium", "home_team": "Honduras", "home_team_id": 96, "away_team": "Mexico", "away_team_id": 10, "home_goals": 1, "away_goals": 1, "halftime_home": 0, "halftime_away": 0, "fulltime_home": 1, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 55, "team": "Honduras", "player": "Romell Quioto", "assist": None, "detail": "Normal Goal"},
        {"minute": 88, "team": "Mexico", "player": "Raúl Jiménez", "assist": None, "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1005, "date": "2026-06-12T18:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "MetLife Stadium", "home_team": "Brazil", "home_team_id": 6, "away_team": "Colombia", "away_team_id": 30, "home_goals": 2, "away_goals": 1, "halftime_home": 1, "halftime_away": 0, "fulltime_home": 2, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 27, "team": "Brazil", "player": "Vinicius Jr.", "assist": "Rodrygo", "detail": "Normal Goal"},
        {"minute": 63, "team": "Colombia", "player": "Luis Díaz", "assist": None, "detail": "Normal Goal"},
        {"minute": 79, "team": "Brazil", "player": "Rodrygo", "assist": None, "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1006, "date": "2026-06-12T21:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "Hard Rock Stadium", "home_team": "Argentina", "home_team_id": 7, "away_team": "Ecuador", "away_team_id": 31, "home_goals": 1, "away_goals": 0, "halftime_home": 0, "halftime_away": 0, "fulltime_home": 1, "fulltime_away": 0, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 67, "team": "Argentina", "player": "Lionel Messi", "assist": "Julián Álvarez", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1007, "date": "2026-06-16T18:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 2", "venue": "MetLife Stadium", "home_team": "Brazil", "home_team_id": 6, "away_team": "Ecuador", "away_team_id": 31, "home_goals": 2, "away_goals": 1, "halftime_home": 1, "halftime_away": 1, "fulltime_home": 2, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 19, "team": "Ecuador", "player": "Enner Valencia", "assist": None, "detail": "Normal Goal"},
        {"minute": 43, "team": "Brazil", "player": "Vinicius Jr.", "assist": None, "detail": "Normal Goal"},
        {"minute": 72, "team": "Brazil", "player": "Endrick", "assist": "Vinicius Jr.", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1008, "date": "2026-06-16T21:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 2", "venue": "Levi's Stadium", "home_team": "Argentina", "home_team_id": 7, "away_team": "Colombia", "away_team_id": 30, "home_goals": 2, "away_goals": 2, "halftime_home": 1, "halftime_away": 2, "fulltime_home": 2, "fulltime_away": 2, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 11, "team": "Colombia", "player": "Luis Díaz", "assist": "James Rodríguez", "detail": "Normal Goal"},
        {"minute": 38, "team": "Colombia", "player": "James Rodríguez", "assist": None, "detail": "Normal Goal"},
        {"minute": 58, "team": "Argentina", "player": "Lionel Messi", "assist": None, "detail": "Penalty"},
        {"minute": 86, "team": "Argentina", "player": "Julián Álvarez", "assist": "Lionel Messi", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1009, "date": "2026-06-13T18:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "Estadio Akron", "home_team": "Germany", "home_team_id": 25, "away_team": "Portugal", "away_team_id": 27, "home_goals": 3, "away_goals": 1, "halftime_home": 2, "halftime_away": 0, "fulltime_home": 3, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 18, "team": "Germany", "player": "Kai Havertz", "assist": "Florian Wirtz", "detail": "Normal Goal"},
        {"minute": 41, "team": "Germany", "player": "Florian Wirtz", "assist": None, "detail": "Normal Goal"},
        {"minute": 69, "team": "Portugal", "player": "Cristiano Ronaldo", "assist": None, "detail": "Penalty"},
        {"minute": 82, "team": "Germany", "player": "Thomas Müller", "assist": "Kai Havertz", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1010, "date": "2026-06-13T21:00:00+00:00", "status": "Match Finished", "status_short": "FT", "elapsed": 90, "round": "Group Stage - 1", "venue": "BC Place", "home_team": "France", "home_team_id": 2, "away_team": "Spain", "away_team_id": 9, "home_goals": 2, "away_goals": 1, "halftime_home": 1, "halftime_away": 0, "fulltime_home": 2, "fulltime_away": 1, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 33, "team": "France", "player": "Kylian Mbappé", "assist": "Antoine Griezmann", "detail": "Normal Goal"},
        {"minute": 57, "team": "Spain", "player": "Pedri", "assist": None, "detail": "Normal Goal"},
        {"minute": 74, "team": "France", "player": "Antoine Griezmann", "assist": None, "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1011, "date": "2026-06-17T18:00:00+00:00", "status": "First Half", "status_short": "1H", "elapsed": 34, "round": "Group Stage - 2", "venue": "Estadio Akron", "home_team": "Germany", "home_team_id": 25, "away_team": "Spain", "away_team_id": 9, "home_goals": 1, "away_goals": 0, "halftime_home": None, "halftime_away": None, "fulltime_home": None, "fulltime_away": None, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": [
        {"minute": 22, "team": "Germany", "player": "Kai Havertz", "assist": "Florian Wirtz", "detail": "Normal Goal"},
    ]},
    {"fixture_id": 1012, "date": "2026-06-17T21:00:00+00:00", "status": "Not Started", "status_short": "NS", "elapsed": None, "round": "Group Stage - 2", "venue": "BC Place", "home_team": "France", "home_team_id": 2, "away_team": "Portugal", "away_team_id": 27, "home_goals": None, "away_goals": None, "halftime_home": None, "halftime_away": None, "fulltime_home": None, "fulltime_away": None, "extratime_home": None, "extratime_away": None, "penalty_home": None, "penalty_away": None, "goal_scorers": []},
]

FAKE_LIVE = [
    {"fixture_id": 1011, "date": "2026-06-17T18:00:00+00:00", "elapsed": 34, "status": "First Half", "round": "Group Stage - 2", "home_team": "Germany", "away_team": "Spain", "home_goals": 1, "away_goals": 0, "goal_scorers": [
        {"minute": 22, "team": "Germany", "player": "Kai Havertz", "assist": "Florian Wirtz", "detail": "Normal Goal"},
    ]},
]

FAKE_TOP_SCORERS = [
    {"rank": 1, "player": "Christian Pulisic", "team": "USA", "goals": 2, "assists": 0},
    {"rank": 2, "player": "Lionel Messi", "team": "Argentina", "goals": 2, "assists": 1},
    {"rank": 3, "player": "Vinicius Jr.", "team": "Brazil", "goals": 2, "assists": 1},
    {"rank": 4, "player": "Raúl Jiménez", "team": "Mexico", "goals": 2, "assists": 0},
    {"rank": 5, "player": "Luis Díaz", "team": "Colombia", "goals": 2, "assists": 0},
    {"rank": 6, "player": "Kai Havertz", "team": "Germany", "goals": 2, "assists": 0},
    {"rank": 7, "player": "Kylian Mbappé", "team": "France", "goals": 1, "assists": 1},
    {"rank": 8, "player": "Folarin Balogun", "team": "USA", "goals": 2, "assists": 0},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path, params=None):
    r = requests.get(f"{API_BASE}{path}", headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _is_testing():
    return request.args.get("testing", "").lower() == "true"


def _parse_fixture(f):
    fixture = f.get("fixture", {})
    teams = f.get("teams", {})
    goals = f.get("goals", {})
    score = f.get("score", {})
    league = f.get("league", {})
    return {
        "fixture_id": fixture.get("id"),
        "date": fixture.get("date"),
        "status": fixture.get("status", {}).get("long"),
        "status_short": fixture.get("status", {}).get("short"),
        "elapsed": fixture.get("status", {}).get("elapsed"),
        "round": league.get("round"),
        "venue": fixture.get("venue", {}).get("name"),
        "home_team": teams.get("home", {}).get("name"),
        "home_team_id": teams.get("home", {}).get("id"),
        "away_team": teams.get("away", {}).get("name"),
        "away_team_id": teams.get("away", {}).get("id"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "halftime_home": score.get("halftime", {}).get("home"),
        "halftime_away": score.get("halftime", {}).get("away"),
        "fulltime_home": score.get("fulltime", {}).get("home"),
        "fulltime_away": score.get("fulltime", {}).get("away"),
        "extratime_home": score.get("extratime", {}).get("home"),
        "extratime_away": score.get("extratime", {}).get("away"),
        "penalty_home": score.get("penalty", {}).get("home"),
        "penalty_away": score.get("penalty", {}).get("away"),
        "goal_scorers": [],
    }


def _fetch_goal_scorers(fixture_ids):
    if not fixture_ids:
        return {}
    result = {}
    for i in range(0, len(fixture_ids), 20):
        batch = fixture_ids[i:i + 20]
        data = _get("/fixtures", {"ids": "-".join(str(x) for x in batch)})
        for f in data.get("response", []):
            fid = f.get("fixture", {}).get("id")
            result[fid] = [
                {
                    "minute": e.get("time", {}).get("elapsed"),
                    "team": e.get("team", {}).get("name"),
                    "player": e.get("player", {}).get("name"),
                    "assist": e.get("assist", {}).get("name"),
                    "detail": e.get("detail"),
                }
                for e in f.get("events", [])
                if e.get("type") == "Goal"
            ]
    return result


def _fetch_top_scorers():
    data = _get("/players/topscorers", {"league": LEAGUE_ID, "season": SEASON})
    result = []
    for i, entry in enumerate(data.get("response", []), 1):
        player = entry.get("player", {})
        stats = entry.get("statistics", [{}])[0]
        result.append({
            "rank": i,
            "player": player.get("name"),
            "team": stats.get("team", {}).get("name"),
            "goals": stats.get("goals", {}).get("total"),
            "assists": stats.get("goals", {}).get("assists"),
        })
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@api_bp.route("/standings")
def standings():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    if _is_testing():
        return jsonify({"standings": FAKE_STANDINGS})

    data = _get("/standings", {"league": LEAGUE_ID, "season": SEASON})
    result = []
    for league_entry in data.get("response", []):
        for group in league_entry.get("league", {}).get("standings", []):
            group_name = group[0].get("group") if group else None
            for entry in group:
                team = entry.get("team", {})
                result.append({
                    "group": group_name,
                    "position": entry.get("rank"),
                    "team_id": team.get("id"),
                    "team": team.get("name"),
                    "logo": team.get("logo"),
                    "played": entry.get("all", {}).get("played"),
                    "win": entry.get("all", {}).get("win"),
                    "draw": entry.get("all", {}).get("draw"),
                    "lose": entry.get("all", {}).get("lose"),
                    "goals_for": entry.get("all", {}).get("goals", {}).get("for"),
                    "goals_against": entry.get("all", {}).get("goals", {}).get("against"),
                    "goal_diff": entry.get("goalsDiff"),
                    "points": entry.get("points"),
                    "form": entry.get("form"),
                })
    return jsonify({"standings": result})


@api_bp.route("/scores")
def scores():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    if _is_testing():
        return jsonify({"fixtures": FAKE_FIXTURES})

    data = _get("/fixtures", {"league": LEAGUE_ID, "season": SEASON})
    return jsonify({"fixtures": [_parse_fixture(f) for f in data.get("response", [])]})


@api_bp.route("/live")
def live():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    if _is_testing():
        return jsonify({"live": FAKE_LIVE})

    data = _get("/fixtures", {"live": "all", "league": LEAGUE_ID})
    results = []
    for f in data.get("response", []):
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        league = f.get("league", {})
        results.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "elapsed": fixture.get("status", {}).get("elapsed"),
            "status": fixture.get("status", {}).get("long"),
            "round": league.get("round"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
            "goal_scorers": [
                {
                    "minute": e.get("time", {}).get("elapsed"),
                    "team": e.get("team", {}).get("name"),
                    "player": e.get("player", {}).get("name"),
                    "assist": e.get("assist", {}).get("name"),
                    "detail": e.get("detail"),
                }
                for e in f.get("events", [])
                if e.get("type") == "Goal"
            ],
        })
    return jsonify({"live": results})


@api_bp.route("/today")
def today():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    today_date = datetime.now(timezone.utc).date().isoformat()

    if _is_testing():
        today_date = "2026-06-17"
        fixtures = [f for f in FAKE_FIXTURES if f["date"].startswith(today_date)]
        top_scorers = FAKE_TOP_SCORERS
    else:
        raw = _get("/fixtures", {"league": LEAGUE_ID, "season": SEASON, "date": today_date})
        fixtures = [_parse_fixture(f) for f in raw.get("response", [])]

        active_ids = [f["fixture_id"] for f in fixtures if f["status_short"] not in ("NS", "TBD")]
        scorers_by_id = _fetch_goal_scorers(active_ids)
        for f in fixtures:
            f["goal_scorers"] = scorers_by_id.get(f["fixture_id"], [])

        top_scorers = _fetch_top_scorers()

    return jsonify({"date": today_date, "fixtures": fixtures, "top_scorers": top_scorers})


@api_bp.route("/yesterday")
def yesterday():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    yesterday_date = (datetime.now(ZoneInfo("US/Eastern")) - timedelta(days=1)).date().isoformat()

    if _is_testing():
        yesterday_date = "2026-06-16"
        fixtures = [f for f in FAKE_FIXTURES if f["date"].startswith(yesterday_date)]
    else:
        raw = _get("/fixtures", {"league": LEAGUE_ID, "season": SEASON, "date": yesterday_date})
        fixtures = [_parse_fixture(f) for f in raw.get("response", [])]

        finished_ids = [f["fixture_id"] for f in fixtures if f["status_short"] == "FT"]
        scorers_by_id = _fetch_goal_scorers(finished_ids)
        for f in fixtures:
            f["goal_scorers"] = scorers_by_id.get(f["fixture_id"], [])

    return jsonify({"date": yesterday_date, "fixtures": fixtures})


@api_bp.route("/update")
def update():
    auth_error = _check_secret()
    if auth_error:
        return auth_error
    if _is_testing():
        live_data = FAKE_LIVE
        fixtures_data = FAKE_FIXTURES
        standings_data = FAKE_STANDINGS
        top_scorers = FAKE_TOP_SCORERS
    else:
        live_raw = _get("/fixtures", {"live": "all", "league": LEAGUE_ID})
        live_data = []
        for f in live_raw.get("response", []):
            fixture = f.get("fixture", {})
            teams = f.get("teams", {})
            goals = f.get("goals", {})
            league = f.get("league", {})
            live_data.append({
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "elapsed": fixture.get("status", {}).get("elapsed"),
                "status": fixture.get("status", {}).get("long"),
                "round": league.get("round"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
                "goal_scorers": [
                    {
                        "minute": e.get("time", {}).get("elapsed"),
                        "team": e.get("team", {}).get("name"),
                        "player": e.get("player", {}).get("name"),
                        "assist": e.get("assist", {}).get("name"),
                        "detail": e.get("detail"),
                    }
                    for e in f.get("events", [])
                    if e.get("type") == "Goal"
                ],
            })

        fixtures_raw = _get("/fixtures", {"league": LEAGUE_ID, "season": SEASON})
        fixtures_data = [_parse_fixture(f) for f in fixtures_raw.get("response", [])]

        standings_raw = _get("/standings", {"league": LEAGUE_ID, "season": SEASON})
        standings_data = []
        for league_entry in standings_raw.get("response", []):
            for group in league_entry.get("league", {}).get("standings", []):
                group_name = group[0].get("group") if group else None
                for entry in group:
                    team = entry.get("team", {})
                    standings_data.append({
                        "group": group_name,
                        "position": entry.get("rank"),
                        "team_id": team.get("id"),
                        "team": team.get("name"),
                        "logo": team.get("logo"),
                        "played": entry.get("all", {}).get("played"),
                        "win": entry.get("all", {}).get("win"),
                        "draw": entry.get("all", {}).get("draw"),
                        "lose": entry.get("all", {}).get("lose"),
                        "goals_for": entry.get("all", {}).get("goals", {}).get("for"),
                        "goals_against": entry.get("all", {}).get("goals", {}).get("against"),
                        "goal_diff": entry.get("goalsDiff"),
                        "points": entry.get("points"),
                        "form": entry.get("form"),
                    })

        top_scorers = _fetch_top_scorers()

    finished = [f for f in fixtures_data if f.get("status_short") == "FT"]
    recent = finished[-5:]

    return jsonify({
        "live": live_data,
        "recent_scores": recent,
        "standings": standings_data,
        "top_scorers": top_scorers,
    })
