"""Weather feed — Environment Canada Citypage XML.

Adapted from the pilot's weather.py. Now reads configuration from the
Campaign model instead of hardcoded constants.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from app.pipeline.exceptions import FeedFetchError, FeedParseError
from app.pipeline.feeds.base import BaseFeed

logger = logging.getLogger(__name__)

DEFAULT_EC_BASE_URL = "https://dd.weather.gc.ca/today/citypage_weather"
DEFAULT_PROVINCE = "BC"
DEFAULT_SITE_CODE = "s0000141"

DEFAULT_PROMPT_TEMPLATE = """\
You are writing a short radio ad script for a weather-sponsored advertisement.

WEATHER DATA:
- Current conditions: {current_conditions}, {current_temp}°C
- {tonight_period}: {tonight_low}°C
- {tomorrow_period}: {tomorrow_conditions}, {tomorrow_high}°C
- {day_after_period}: {day_after_conditions}, {day_after_high}°C / {day_after_low}°C

ADVERTISER:
- Name: {advertiser_name}
- Description: {advertiser_description}
- Tagline: {advertiser_tagline}
- Call to action: {advertiser_cta}
- Seasonal hook: {seasonal_hook}

{pronunciation_section}\
INSTRUCTIONS:
- Write a natural, conversational script approximately {target_seconds} seconds long when read aloud (approximately {target_words} words)
- Start with the weather report — current conditions, tonight's low, tomorrow's outlook, and a one-day lookahead
- Write a single smooth transition sentence that bridges the weather to the advertiser
- Close with the advertiser name, tagline, and call to action
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if a friendly local radio announcer is speaking
{pronunciation_instruction}\
- Output only the final script, nothing else\
"""


class WeatherFeed(BaseFeed):
    def fetch(self, campaign) -> dict:
        """Fetch weather data from Environment Canada."""
        config = campaign.feed_config or {}
        province = config.get("province", DEFAULT_PROVINCE)
        site_code = config.get("site_code", DEFAULT_SITE_CODE)
        base_url = campaign.feed_url or f"{DEFAULT_EC_BASE_URL}/{province}"
        city = campaign.target_city or "Vancouver"

        logger.info("Fetching weather for %s (%s)...", city, site_code)

        xml_url = self._find_latest_xml_url(base_url, site_code)

        try:
            resp = requests.get(xml_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FeedFetchError(f"Failed to fetch weather XML: {exc}") from exc

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            raise FeedParseError(f"Failed to parse weather XML: {exc}") from exc

        return self._parse_xml(root)

    def default_prompt_template(self) -> str:
        return DEFAULT_PROMPT_TEMPLATE

    # ---- internals ----

    def _find_latest_xml_url(self, base_url: str, site_code: str) -> str:
        now_utc = datetime.now(timezone.utc)
        hours_to_try = [now_utc.hour, (now_utc.hour - 1) % 24]

        for hour in hours_to_try:
            hh = f"{hour:02d}"
            dir_url = f"{base_url}/{hh}/"

            try:
                resp = requests.get(dir_url, timeout=10)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
            except requests.RequestException:
                continue

            pattern = re.compile(
                rf'href="([^"]*_CitypageWeather_{site_code}_en\.xml)"'
            )
            matches = pattern.findall(resp.text)
            if not matches:
                continue

            latest_file = sorted(matches)[-1]
            return f"{base_url}/{hh}/{latest_file}"

        raise FeedFetchError(
            f"Could not find weather XML for site {site_code} "
            f"in the last two hours of the EC feed."
        )

    def _parse_xml(self, root) -> dict:
        cc = root.find("currentConditions")
        if cc is None:
            raise FeedParseError("No <currentConditions> in feed.")

        current_conditions = _text(cc, "condition", "Unknown")
        current_temp = _text(cc, "temperature", "?")

        fg = root.find("forecastGroup")
        if fg is None:
            raise FeedParseError("No <forecastGroup> in feed.")

        forecasts = fg.findall("forecast")
        if len(forecasts) < 3:
            raise FeedParseError(
                f"Expected at least 3 forecasts, got {len(forecasts)}."
            )

        fc0, fc1, fc2 = forecasts[0], forecasts[1], forecasts[2]

        return {
            "current_conditions": current_conditions,
            "current_temp": current_temp,
            "tonight_period": _period_name(fc0),
            "tonight_low": _forecast_temp(fc0),
            "tomorrow_period": _period_name(fc1),
            "tomorrow_conditions": _abbreviated_conditions(fc1),
            "tomorrow_high": _forecast_temp(fc1),
            "day_after_period": _period_name(fc2),
            "day_after_conditions": _abbreviated_conditions(fc2),
            "day_after_high": _forecast_temp(fc2),
            "day_after_low": _forecast_temp_by_class(fc2, "low"),
        }


# ---- XML helpers (unchanged from pilot) ----

def _text(parent, tag, default=""):
    el = parent.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return default


def _period_name(forecast_el):
    period_el = forecast_el.find("period")
    if period_el is not None:
        name = period_el.get("textForecastName", "")
        if name:
            return name
        if period_el.text:
            return period_el.text.strip()
    return "Unknown"


def _abbreviated_conditions(forecast_el):
    abbr = forecast_el.find("abbreviatedForecast")
    if abbr is not None:
        ts = abbr.find("textSummary")
        if ts is not None and ts.text:
            return ts.text.strip()
    return _text(forecast_el, "textSummary", "")


def _forecast_temp(forecast_el):
    temps = forecast_el.find("temperatures")
    if temps is not None:
        temp_el = temps.find("temperature")
        if temp_el is not None and temp_el.text:
            return temp_el.text.strip()
    return "?"


def _forecast_temp_by_class(forecast_el, cls):
    temps = forecast_el.find("temperatures")
    if temps is not None:
        for t in temps.findall("temperature"):
            if t.get("class") == cls and t.text:
                return t.text.strip()
        temp_el = temps.find("temperature")
        if temp_el is not None and temp_el.text:
            return temp_el.text.strip()
    return "?"
