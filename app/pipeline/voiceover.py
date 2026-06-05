"""Generate voiceover audio via the ElevenLabs API."""

import logging

from elevenlabs.client import ElevenLabs
from flask import current_app

from app.models.campaign import PRESET_VOICES
from app.pipeline.exceptions import VoiceoverGenerationError

logger = logging.getLogger(__name__)


def generate_voiceover(script: str, voice_id: str, is_custom: bool = False) -> bytes:
    """Generate voiceover MP3 from script text.

    Args:
        script: The ad script text to convert to speech.
        voice_id: ElevenLabs voice ID to use.

    Returns:
        Raw MP3 bytes.

    Raises:
        VoiceoverGenerationError: If the TTS call fails.
    """
    client = ElevenLabs(
        api_key=current_app.config["ELEVENLABS_API_KEY"]
    )

    voice_id = (voice_id or "").strip()
    if not voice_id:
        raise VoiceoverGenerationError("voice_id is empty — check campaign voice settings.")

    if is_custom:
        model_id = current_app.config["ELEVENLABS_CUSTOM_MODEL"]
    else:
        model_id = current_app.config["ELEVENLABS_MODEL"]

    logger.info("Generating voiceover — voice_id=%r  model=%s  custom=%s",
                voice_id, model_id, is_custom)

    try:
        audio_iterator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=script,
            model_id=model_id,
        )
    except Exception as exc:
        raise VoiceoverGenerationError(
            f"ElevenLabs TTS call failed: {exc}"
        ) from exc

    # Collect all chunks into bytes
    chunks = []
    for chunk in audio_iterator:
        chunks.append(chunk)

    audio_bytes = b"".join(chunks)
    logger.info("Voiceover generated (%d bytes)", len(audio_bytes))
    return audio_bytes
