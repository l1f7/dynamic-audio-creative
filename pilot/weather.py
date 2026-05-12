"""Fetch and parse the Environment Canada Citypage Weather XML feed.

The feed lives at:
  https://dd.weather.gc.ca/today/citypage_weather/BC/{HH}/
where {HH} is the current UTC hour (zero-padded). Inside each hour directory,
files are named like:
  20260506T180141.319Z_MSC_CitypageWeather_s0000141_en.xml

This module lists the directory for the current UTC hour, finds the most
recent English XML for the configured site code, and parses it.
"""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

# Environment Canada feed — weather-specific constants
EC_BASE_URL = "https://dd.weather.gc.ca/today/citypage_weather/BC"
SITE_CODE = "s0000141"
CITY_NAME = "Vancouver"

# Advertiser placeholder for the weather campaign
WEATHER_ADVERTISER = {
    "advertiser_name": "Mountain Equipment Co-op",
    "advertiser_tagline": "For the love of the outdoors",
    "advertiser_cta": "Visit MEC.ca or your nearest store",
    "seasonal_hook": "Spring hiking season is here",
}

# Prompt template for weather-sponsored ads
WEATHER_PROMPT_TEMPLATE = """\
You are writing a short radio ad script for a weather-sponsored advertisement.

WEATHER DATA:
- Current conditions: {current_conditions}, {current_temp}°C
- {tonight_period}: {tonight_low}°C
- {tomorrow_period}: {tomorrow_conditions}, {tomorrow_high}°C
- {day_after_period}: {day_after_conditions}, {day_after_high}°C / {day_after_low}°C

ADVERTISER:
- Name: {advertiser_name}
- Tagline: {advertiser_tagline}
- Call to action: {advertiser_cta}
- Seasonal hook: {seasonal_hook}

INSTRUCTIONS:
- Write a natural, conversational script approximately {target_seconds} seconds long when read aloud (approximately {target_words} words)
- Start with the weather report — current conditions, tonight's low, tomorrow's outlook, and a one-day lookahead
- Write a single smooth transition sentence that bridges the weather to the advertiser
- Close with the advertiser name, tagline, and call to action
- Do not use any formatting, headers, or stage directions — plain flowing text only
- Write as if a friendly local radio announcer is speaking
- Output only the final script, nothing else

NOTE: This is a test script for prototype purposes only. Advertiser details are placeholder data.\
"""


def fetch_weather() -> dict:
    """Fetch current weather data for Vancouver from Environment Canada.

    Returns a dict with keys:
        current_conditions, current_temp,
        tonight_period, tonight_low,
        tomorrow_period, tomorrow_conditions, tomorrow_high,
        day_after_period, day_after_conditions, day_after_high, day_after_low
    """
    print(f"Fetching weather for {CITY_NAME} ({SITE_CODE})...")

    xml_url = _find_latest_xml_url()

    try:
        resp = requests.get(xml_url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Failed to fetch weather XML: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        print(f"ERROR: Failed to parse weather XML: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Current conditions ---
    cc = root.find("currentConditions")
    if cc is None:
        print("ERROR: No <currentConditions> in feed.", file=sys.stderr)
        sys.exit(1)

    current_conditions = _text(cc, "condition", "Unknown")
    current_temp = _text(cc, "temperature", "?")

    # --- Forecasts ---
    fg = root.find("forecastGroup")
    if fg is None:
        print("ERROR: No <forecastGroup> in feed.", file=sys.stderr)
        sys.exit(1)

    forecasts = fg.findall("forecast")
    if len(forecasts) < 3:
        print(
            f"ERROR: Expected at least 3 forecasts, got {len(forecasts)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # EC feed order varies by time of day. Use the first three forecasts
    # (e.g. Today/Tonight/Tomorrow during the day, Tonight/Tomorrow/Tomorrow night
    # in the evening). The ad prompt template uses the period names directly.
    fc0 = forecasts[0]
    fc1 = forecasts[1]
    fc2 = forecasts[2]

    data = {
        "current_conditions": current_conditions,
        "current_temp": current_temp,
        # Forecast slot 0 (tonight or today)
        "tonight_period": _period_name(fc0),
        "tonight_low": _forecast_temp(fc0),
        # Forecast slot 1 (tomorrow or tonight)
        "tomorrow_period": _period_name(fc1),
        "tomorrow_conditions": _abbreviated_conditions(fc1),
        "tomorrow_high": _forecast_temp(fc1),
        # Forecast slot 2 (day after or tomorrow)
        "day_after_period": _period_name(fc2),
        "day_after_conditions": _abbreviated_conditions(fc2),
        "day_after_high": _forecast_temp(fc2),
        "day_after_low": _forecast_temp_by_class(fc2, "low"),
    }

    print(
        f"Current: {data['current_conditions']}, {data['current_temp']}°C | "
        f"{data['tonight_period']} low: {data['tonight_low']}°C | "
        f"{data['tomorrow_period']}: {data['tomorrow_conditions']}, {data['tomorrow_high']}°C | "
        f"{data['day_after_period']}: {data['day_after_conditions']}, "
        f"{data['day_after_high']}°C / {data['day_after_low']}°C"
    )

    return data


# ---- feed discovery ----

def _find_latest_xml_url() -> str:
    """List the current UTC hour directory and return the URL of the most recent
    English XML file for our site code.

    Falls back to the previous hour if the current hour directory is empty or
    doesn't exist yet.
    """
    now_utc = datetime.now(timezone.utc)
    hours_to_try = [now_utc.hour, (now_utc.hour - 1) % 24]

    for hour in hours_to_try:
        hh = f"{hour:02d}"
        dir_url = f"{EC_BASE_URL}/{hh}/"

        try:
            resp = requests.get(dir_url, timeout=10)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
        except requests.RequestException:
            continue

        # Parse the directory listing HTML for filenames matching our site
        pattern = re.compile(
            rf'href="([^"]*_CitypageWeather_{SITE_CODE}_en\.xml)"'
        )
        matches = pattern.findall(resp.text)
        if not matches:
            continue

        # Files are timestamped — take the last one (most recent)
        latest_file = sorted(matches)[-1]
        return f"{EC_BASE_URL}/{hh}/{latest_file}"

    print(
        f"ERROR: Could not find weather XML for site {SITE_CODE} "
        f"in the last two hours of the EC feed.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---- XML helpers ----

def _text(parent, tag: str, default: str = "") -> str:
    """Return the text of a direct child element, or default."""
    el = parent.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return default


def _period_name(forecast_el) -> str:
    """Return the forecast period name (e.g. 'Tonight', 'Thursday').

    Uses the textForecastName attribute on <period>, falling back to the
    element text.
    """
    period_el = forecast_el.find("period")
    if period_el is not None:
        name = period_el.get("textForecastName", "")
        if name:
            return name
        if period_el.text:
            return period_el.text.strip()
    return "Unknown"


def _abbreviated_conditions(forecast_el) -> str:
    """Return the short condition summary from abbreviatedForecast."""
    abbr = forecast_el.find("abbreviatedForecast")
    if abbr is not None:
        ts = abbr.find("textSummary")
        if ts is not None and ts.text:
            return ts.text.strip()
    # Fall back to the full textSummary
    return _text(forecast_el, "textSummary", "")


def _forecast_temp(forecast_el) -> str:
    """Extract the first temperature value from a <forecast> element's <temperatures>."""
    temps = forecast_el.find("temperatures")
    if temps is not None:
        temp_el = temps.find("temperature")
        if temp_el is not None and temp_el.text:
            return temp_el.text.strip()
    return "?"


def _forecast_temp_by_class(forecast_el, cls: str) -> str:
    """Extract a temperature by class ('high' or 'low') from a <forecast> element.

    Falls back to the first temperature if the requested class isn't found.
    """
    temps = forecast_el.find("temperatures")
    if temps is not None:
        for t in temps.findall("temperature"):
            if t.get("class") == cls and t.text:
                return t.text.strip()
        # Fallback: return whatever temperature is there
        temp_el = temps.find("temperature")
        if temp_el is not None and temp_el.text:
            return temp_el.text.strip()
    return "?"
