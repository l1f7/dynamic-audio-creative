"""Tests for feed data parsing — weather XML and concert JSON.

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
