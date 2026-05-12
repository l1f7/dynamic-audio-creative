#!/usr/bin/env python3
"""Dynamic Audio Creative Pipeline — Pilot

Generates broadcast-ready radio ads from live data feeds.

Usage:
    python main.py              # defaults to weather
    python main.py weather      # weather-sponsored ad (MEC pilot)
    python main.py concerts     # concert update ad (venue pilot)
"""

import sys

from dotenv import load_dotenv

load_dotenv()  # Load .env before anything that reads env vars

from script_gen import generate_script
from voiceover import generate_voiceover
from mixer import mix_audio

AVAILABLE_CAMPAIGNS = ["weather", "concerts"]


def main():
    campaign = sys.argv[1] if len(sys.argv) > 1 else "weather"

    # Mix settings defaults
    mix_opts = {"intro_seconds": 2.0, "outro_seconds": 2.0, "duck_volume": 0.2}

    if campaign == "weather":
        from weather import fetch_weather, WEATHER_PROMPT_TEMPLATE, WEATHER_ADVERTISER

        data = fetch_weather()
        advertiser = WEATHER_ADVERTISER
        template = WEATHER_PROMPT_TEMPLATE
        music_bed = "./assets/music_bed_weather.mp3"
        output_dir = "./output/weather"
        voice = "Brian"

    elif campaign == "concerts":
        from concerts import fetch_concerts, CONCERT_PROMPT_TEMPLATE

        data = fetch_concerts()
        advertiser = {}  # venue is the sponsor — all sponsor fields are in data already
        template = CONCERT_PROMPT_TEMPLATE
        music_bed = "./assets/music_bed_concerts.mp3"
        output_dir = "./output/concerts"
        mix_opts["intro_seconds"] = 3.0  # let the music hit a bit longer
        voice = "Tyler Cruz"

    else:
        print(f"Unknown campaign: {campaign}", file=sys.stderr)
        print(f"Available: {', '.join(AVAILABLE_CAMPAIGNS)}")
        sys.exit(1)

    # Merge data + advertiser + production params
    template_vars = {
        **data,
        **advertiser,
        "target_seconds": 30,
        "target_words": 75,
    }

    voiceover_path = f"{output_dir}/voiceover.mp3"
    final_ad_path = f"{output_dir}/final_ad.mp3"

    # Pipeline: generate script → voiceover → mix with music bed
    script = generate_script(template, template_vars)
    generate_voiceover(script, output_dir, voiceover_path, voice_primary=voice)
    mix_audio(music_bed, voiceover_path, final_ad_path, output_dir, **mix_opts)

    print(f"Done. Output: {final_ad_path}")


if __name__ == "__main__":
    main()
