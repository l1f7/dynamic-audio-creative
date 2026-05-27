"""Tests for feed data parsing — weather XML, concert JSON, and World Cup JSON.

These test the parsing logic from the pilot modules with sample data,
without hitting external APIs.
"""

import json
import xml.etree.ElementTree as ET

import pytest

# Import pilot parsing helpers directly
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pilot"))

from app.pipeline.feeds.world_cup import (
    _build_template_vars,
    _build_tone_guidance,
    _format_fixture,
    _format_scorers,
)


class TestWeatherParsing:
    """Test Environment Canada XML parsing helpers."""

    SAMPLE_XML = """\
    <siteData>
      <currentConditions>
        <condition>Cloudy</condition>
        <temperature unitType="metric" units="C">13.8</temperature>
      </currentConditions>
      <forecastGroup>
        <forecast>
          <period textForecastName="Today">Wednesday</period>
          <textSummary>Mainly cloudy. High 18.</textSummary>
          <abbreviatedForecast>
            <textSummary>A mix of sun and cloud</textSummary>
          </abbreviatedForecast>
          <temperatures>
            <temperature unitType="metric" units="C" class="high">18</temperature>
          </temperatures>
        </forecast>
        <forecast>
          <period textForecastName="Tonight">Wednesday night</period>
          <textSummary>A few clouds. Low 11.</textSummary>
          <abbreviatedForecast>
            <textSummary>Partly cloudy</textSummary>
          </abbreviatedForecast>
          <temperatures>
            <temperature unitType="metric" units="C" class="low">11</temperature>
          </temperatures>
        </forecast>
        <forecast>
          <period textForecastName="Thursday">Thursday</period>
          <textSummary>Mainly cloudy. High 18.</textSummary>
          <abbreviatedForecast>
            <textSummary>Mainly cloudy</textSummary>
          </abbreviatedForecast>
          <temperatures>
            <temperature unitType="metric" units="C" class="high">18</temperature>
          </temperatures>
        </forecast>
      </forecastGroup>
    </siteData>
    """

    def test_parse_current_conditions(self):
        from weather import _text

        root = ET.fromstring(self.SAMPLE_XML)
        cc = root.find("currentConditions")

        assert _text(cc, "condition", "Unknown") == "Cloudy"
        assert _text(cc, "temperature", "?") == "13.8"

    def test_parse_period_name(self):
        from weather import _period_name

        root = ET.fromstring(self.SAMPLE_XML)
        forecasts = root.find("forecastGroup").findall("forecast")

        assert _period_name(forecasts[0]) == "Today"
        assert _period_name(forecasts[1]) == "Tonight"
        assert _period_name(forecasts[2]) == "Thursday"

    def test_parse_abbreviated_conditions(self):
        from weather import _abbreviated_conditions

        root = ET.fromstring(self.SAMPLE_XML)
        forecasts = root.find("forecastGroup").findall("forecast")

        assert _abbreviated_conditions(forecasts[0]) == "A mix of sun and cloud"
        assert _abbreviated_conditions(forecasts[1]) == "Partly cloudy"

    def test_parse_forecast_temp(self):
        from weather import _forecast_temp

        root = ET.fromstring(self.SAMPLE_XML)
        forecasts = root.find("forecastGroup").findall("forecast")

        assert _forecast_temp(forecasts[0]) == "18"
        assert _forecast_temp(forecasts[1]) == "11"

    def test_parse_forecast_temp_by_class(self):
        from weather import _forecast_temp_by_class

        root = ET.fromstring(self.SAMPLE_XML)
        forecasts = root.find("forecastGroup").findall("forecast")

        assert _forecast_temp_by_class(forecasts[0], "high") == "18"
        assert _forecast_temp_by_class(forecasts[1], "low") == "11"
        # Asking for a class that doesn't exist falls back to first temp
        assert _forecast_temp_by_class(forecasts[0], "low") == "18"

    def test_missing_element_returns_default(self):
        from weather import _text

        root = ET.fromstring("<parent><child>hello</child></parent>")
        parent = root if root.tag == "parent" else root.find("parent")
        assert _text(root, "nonexistent", "fallback") == "fallback"


class TestConcertJsonParsing:
    """Test AdmitOne JSON feed parsing."""

    SAMPLE_JSON = {
        "events": [
            {
                "title": "Chet Faker",
                "artist": "Chet Faker",
                "venue": "Vogue Theatre",
                "city": "Vancouver",
                "event_date": "May 8th, 2026",
                "sold_out": False,
                "cancelled": False,
            },
            {
                "title": "Cancelled Show",
                "artist": "Nobody",
                "venue": "Biltmore",
                "city": "Vancouver",
                "event_date": "May 9th, 2026",
                "sold_out": False,
                "cancelled": True,
            },
            {
                "title": "Snail Mail",
                "artist": "Snail Mail",
                "venue": "Vogue Theatre",
                "city": "Vancouver",
                "event_date": "May 10th, 2026",
                "sold_out": True,
                "cancelled": False,
            },
        ]
    }

    def test_parse_json_feed(self):
        from concerts import _parse_json_feed

        shows = _parse_json_feed(json.dumps(self.SAMPLE_JSON), venue_filter="")

        # Cancelled shows are excluded
        assert len(shows) == 2
        assert shows[0]["artist"] == "Chet Faker"
        assert shows[1]["artist"] == "Snail Mail"

    def test_parse_json_feed_sold_out_noted(self):
        from concerts import _parse_json_feed

        shows = _parse_json_feed(json.dumps(self.SAMPLE_JSON), venue_filter="")
        snail_mail = [s for s in shows if s["artist"] == "Snail Mail"][0]
        assert snail_mail.get("note") == "SOLD OUT"

    def test_parse_json_feed_venue_filter(self):
        from concerts import _parse_json_feed

        shows = _parse_json_feed(
            json.dumps(self.SAMPLE_JSON), venue_filter="Vogue Theatre"
        )
        assert all(s["venue"] == "Vogue Theatre" for s in shows)

    def test_parse_json_feed_empty(self):
        from concerts import _parse_json_feed

        shows = _parse_json_feed('{"events": []}', venue_filter="")
        assert shows == []

    def test_parse_json_feed_invalid_json(self):
        from concerts import _parse_json_feed

        shows = _parse_json_feed("not json at all", venue_filter="")
        assert shows == []

    def test_build_template_vars(self):
        from concerts import _build_template_vars

        shows = [
            {"artist": "Chet Faker", "date": "May 8th", "venue": "Vogue Theatre"},
            {"artist": "Snail Mail", "date": "May 10th", "venue": "Vogue Theatre"},
        ]
        data = _build_template_vars(shows)

        assert data["next_artist"] == "Chet Faker"
        assert data["next_date"] == "May 8th"
        assert data["num_shows"] == 2
        assert "Chet Faker" in data["upcoming_shows_formatted"]
        assert "Snail Mail" in data["upcoming_shows_formatted"]

    def test_looks_like_json(self):
        from concerts import _looks_like_json

        assert _looks_like_json('{"events": []}') is True
        assert _looks_like_json('[{"a": 1}]') is True
        assert _looks_like_json('  {"events": []}') is True
        assert _looks_like_json("<html>") is False
        assert _looks_like_json("not json") is False


class TestWorldCupParsing:
    """Test /today proxy response parsing helpers."""

    FINISHED = {
        "fixture_id": 1009,
        "date": "2026-06-13T18:00:00+00:00",
        "status": "Match Finished",
        "status_short": "FT",
        "elapsed": 90,
        "round": "Group Stage - 1",
        "venue": "Estadio Akron",
        "home_team": "Germany",
        "away_team": "Portugal",
        "home_goals": 3,
        "away_goals": 1,
        "halftime_home": 2,
        "halftime_away": 0,
        "fulltime_home": 3,
        "fulltime_away": 1,
        "extratime_home": None,
        "extratime_away": None,
        "penalty_home": None,
        "penalty_away": None,
        "goal_scorers": [
            {"minute": 18, "team": "Germany", "player": "Kai Havertz", "assist": "Florian Wirtz", "detail": "Normal Goal"},
            {"minute": 69, "team": "Portugal", "player": "Cristiano Ronaldo", "assist": None, "detail": "Penalty"},
            {"minute": 82, "team": "Germany", "player": "Thomas Müller", "assist": "Kai Havertz", "detail": "Normal Goal"},
        ],
    }

    LIVE = {
        "fixture_id": 1011,
        "date": "2026-06-17T18:00:00+00:00",
        "status": "First Half",
        "status_short": "1H",
        "elapsed": 34,
        "round": "Group Stage - 2",
        "venue": "Estadio Akron",
        "home_team": "Germany",
        "away_team": "Spain",
        "home_goals": 1,
        "away_goals": 0,
        "halftime_home": None,
        "halftime_away": None,
        "fulltime_home": None,
        "fulltime_away": None,
        "extratime_home": None,
        "extratime_away": None,
        "penalty_home": None,
        "penalty_away": None,
        "goal_scorers": [
            {"minute": 22, "team": "Germany", "player": "Kai Havertz", "assist": "Florian Wirtz", "detail": "Normal Goal"},
        ],
    }

    NOT_STARTED = {
        "fixture_id": 1012,
        "date": "2026-06-17T21:00:00+00:00",
        "status": "Not Started",
        "status_short": "NS",
        "elapsed": None,
        "round": "Group Stage - 2",
        "venue": "BC Place",
        "home_team": "France",
        "away_team": "Portugal",
        "home_goals": None,
        "away_goals": None,
        "halftime_home": None,
        "halftime_away": None,
        "fulltime_home": None,
        "fulltime_away": None,
        "extratime_home": None,
        "extratime_away": None,
        "penalty_home": None,
        "penalty_away": None,
        "goal_scorers": [],
    }

    DRAW = {
        **FINISHED,
        "home_team": "Argentina",
        "away_team": "Colombia",
        "home_goals": 2,
        "away_goals": 2,
        "goal_scorers": [],
    }

    TOP_SCORERS = [
        {"rank": 1, "player": "Christian Pulisic", "team": "USA", "goals": 2, "assists": 0},
        {"rank": 2, "player": "Lionel Messi", "team": "Argentina", "goals": 2, "assists": 1},
    ]

    def test_format_fixture_finished(self):
        line = _format_fixture(self.FINISHED)
        assert "Portugal" in line
        assert "Germany" in line
        assert "1-3" in line
        assert "FT" in line
        assert "Group Stage - 1" in line

    def test_format_fixture_finished_includes_scorers(self):
        line = _format_fixture(self.FINISHED)
        assert "Kai Havertz" in line
        assert "Cristiano Ronaldo" in line
        assert "Penalty" in line

    def test_format_fixture_live(self):
        line = _format_fixture(self.LIVE)
        assert "Spain" in line
        assert "Germany" in line
        assert "LIVE" in line
        assert "34'" in line
        assert "0-1" in line

    def test_format_fixture_not_started(self):
        line = _format_fixture(self.NOT_STARTED)
        assert "Portugal" in line
        assert "France" in line
        assert "21:00 UTC" in line
        # No score
        assert "None" not in line

    def test_format_scorers_normal_goal(self):
        scorers = [{"minute": 18, "team": "Germany", "player": "Kai Havertz", "assist": None, "detail": "Normal Goal"}]
        result = _format_scorers(scorers)
        assert "Kai Havertz" in result
        assert "18'" in result
        assert "Normal Goal" not in result  # suppressed for normal goals

    def test_format_scorers_penalty(self):
        scorers = [{"minute": 69, "team": "Portugal", "player": "Cristiano Ronaldo", "assist": None, "detail": "Penalty"}]
        result = _format_scorers(scorers)
        assert "Penalty" in result

    def test_format_scorers_empty(self):
        assert _format_scorers([]) == ""

    def test_tone_guidance_dominant_win(self):
        # 2-goal differential = comfortable
        guidance = _build_tone_guidance([self.FINISHED])
        assert "Germany" in guidance
        assert "Portugal" in guidance
        assert "2 goals" in guidance

    def test_tone_guidance_draw(self):
        guidance = _build_tone_guidance([self.DRAW])
        assert "draw" in guidance.lower()

    def test_tone_guidance_skips_non_finished(self):
        guidance = _build_tone_guidance([self.LIVE, self.NOT_STARTED])
        assert guidance == ""

    def test_build_template_vars_counts(self):
        fixtures = [self.FINISHED, self.LIVE, self.NOT_STARTED]
        data = _build_template_vars(fixtures, self.TOP_SCORERS, "2026-06-17")

        assert data["num_fixtures"] == 3
        assert data["num_finished"] == 1
        assert data["num_live"] == 1
        assert data["match_date"] == "2026-06-17"

    def test_build_template_vars_formatted_content(self):
        data = _build_template_vars([self.FINISHED], self.TOP_SCORERS, "2026-06-17")

        assert "Germany" in data["fixtures_formatted"]
        assert "Christian Pulisic" in data["top_scorers_formatted"]
        assert "Lionel Messi" in data["top_scorers_formatted"]

    def test_build_template_vars_no_fixtures(self):
        data = _build_template_vars([], self.TOP_SCORERS, "2026-06-17")
        assert data["fixtures_formatted"] == "No matches today."
        assert data["num_fixtures"] == 0

    def test_build_template_vars_top_scorers_capped_at_5(self):
        many_scorers = [
            {"rank": i, "player": f"Player {i}", "team": "Team", "goals": 3 - i // 2, "assists": 0}
            for i in range(1, 9)
        ]
        data = _build_template_vars([], many_scorers, "2026-06-17")
        lines = data["top_scorers_formatted"].strip().split("\n")
        assert len(lines) == 5
