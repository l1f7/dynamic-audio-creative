"""Generate voiceover audio via the ElevenLabs API."""

import os
import sys

from elevenlabs.client import ElevenLabs

from config import ELEVENLABS_MODEL

# Well-known ElevenLabs pre-built voice IDs.
# Using these directly avoids needing the voices_read API permission.
VOICE_IDS = {
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Eric": "cjVigY5qzO86Huf0OWal",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "James": "ZQe5CZNOzWyzPSCn5a3c",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Will": "bIHbv24MWmeRgasZH58o",
    "Tyler Cruz": "SA7eD52NRr8WAehitVt1",
}


def generate_voiceover(
    script: str,
    output_dir: str,
    voiceover_path: str,
    voice_primary: str = "Brian",
    voice_fallback: str = "Charlie",
) -> str:
    """Generate voiceover MP3 from script text.

    Args:
        script: The ad script text to convert to speech.
        output_dir: Directory to ensure exists for output.
        voiceover_path: Full path for the output voiceover file.
        voice_primary: Name of the primary ElevenLabs voice.
        voice_fallback: Name of the fallback voice if primary isn't available.

    Returns:
        Path to the saved voiceover file.
    """
    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))

    # Resolve voice ID from our lookup table
    voice_id = VOICE_IDS.get(voice_primary)
    voice_used = voice_primary
    if not voice_id:
        print(f"  Voice '{voice_primary}' not in lookup table, trying '{voice_fallback}'...")
        voice_id = VOICE_IDS.get(voice_fallback)
        voice_used = voice_fallback
    if not voice_id:
        print(
            f"ERROR: Neither '{voice_primary}' nor '{voice_fallback}' "
            f"found in voice ID table.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Generating voiceover via ElevenLabs ({voice_used})...")

    try:
        audio_iterator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=script,
            model_id=ELEVENLABS_MODEL,
        )
    except Exception as exc:
        print(f"ERROR: ElevenLabs TTS call failed: {exc}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # The SDK returns an iterator of bytes chunks
    with open(voiceover_path, "wb") as f:
        for chunk in audio_iterator:
            f.write(chunk)

    print(f"Voiceover saved to {voiceover_path}")
    return voiceover_path
