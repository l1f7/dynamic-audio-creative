"""Mix voiceover with background music bed using FFmpeg.

Works with bytes in/out using temp files — no persistent filesystem needed.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from app.pipeline.exceptions import MixingError

logger = logging.getLogger(__name__)


def mix_audio(
    music_bed_bytes: bytes,
    voiceover_bytes: bytes,
    intro_seconds: float = 2.0,
    outro_seconds: float = 2.0,
    duck_volume: float = 0.2,
    duck_fade: float = 0.5,
    target_seconds: float | None = None,
) -> tuple[bytes, float]:
    """Mix voiceover with a music bed and return the final ad as bytes.

    Args:
        music_bed_bytes: Raw MP3 bytes of the background music.
        voiceover_bytes: Raw MP3 bytes of the voiceover.
        intro_seconds: Music plays at full volume before voice starts.
        outro_seconds: Music fades back up then out after voice ends.
        duck_volume: Music volume during voiceover (0.0-1.0).
        duck_fade: Seconds to ramp between full and ducked volume.
        target_seconds: Target final ad duration. Any voiceover that would push
            the final ad over this is time-stretched to fit, regardless of how
            far over it is (e.g. a 60s voiceover is retimed down to fit a 30s
            target). None disables stretching.

    Returns:
        A ``(final_ad_bytes, stretch_factor)`` tuple. ``stretch_factor`` is the
        FFmpeg atempo applied to the voiceover to fit the target (>1.0 = sped
        up); 1.0 when no stretching was needed.

    Raises:
        MixingError: If FFmpeg fails.
    """
    stretch_factor = 1.0
    with tempfile.TemporaryDirectory() as tmpdir:
        vo_path = Path(tmpdir) / "voiceover.mp3"
        music_path = Path(tmpdir) / "music_bed.mp3"
        output_path = Path(tmpdir) / "final_ad.mp3"

        vo_path.write_bytes(voiceover_bytes)
        music_path.write_bytes(music_bed_bytes)

        # Probe voiceover duration
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(vo_path),
        ]
        try:
            result = subprocess.run(
                probe_cmd, capture_output=True, text=True, check=True
            )
            vo_duration = float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as exc:
            raise MixingError(
                f"Could not determine voiceover duration: {exc}"
            ) from exc

        # Time-stretch voiceover if it would push the final ad over target
        if target_seconds is not None:
            target_vo_duration = target_seconds - intro_seconds - outro_seconds
            final_ad_duration = vo_duration + intro_seconds + outro_seconds
            if vo_duration > target_vo_duration and target_vo_duration > 0:
                atempo = vo_duration / target_vo_duration
                stretch_factor = atempo
                logger.info(
                    "Stretching voiceover %.2fs → %.2fs (atempo=%.4f, final ad %.2fs → %.2fs)",
                    vo_duration, target_vo_duration, atempo, final_ad_duration, target_seconds,
                )
                stretched_path = Path(tmpdir) / "voiceover_stretched.mp3"
                stretch_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(vo_path),
                    "-filter:a", f"atempo={atempo:.6f}",
                    "-b:a", "192k",
                    str(stretched_path),
                ]
                try:
                    subprocess.run(stretch_cmd, capture_output=True, text=True, check=True)
                except subprocess.CalledProcessError as exc:
                    raise MixingError(f"FFmpeg time-stretch failed: {exc.stderr}") from exc
                vo_path = stretched_path
                vo_duration = target_vo_duration

        # Build the filter graph
        total_duration = intro_seconds + vo_duration + outro_seconds
        intro_ms = int(intro_seconds * 1000)

        duck_start = intro_seconds
        duck_end = intro_seconds + vo_duration
        dv = duck_volume
        df = duck_fade

        vol_expr = (
            f"if(lt(t,{duck_start}),1,"
            f"if(lt(t,{duck_start + df}),1-(1-{dv})*(t-{duck_start})/{df},"
            f"if(lt(t,{duck_end}),{dv},"
            f"if(lt(t,{duck_end + df}),{dv}+(1-{dv})*(t-{duck_end})/{df},"
            f"1))))"
        )

        filter_complex = (
            f"[1:a]atrim=0:{total_duration},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={intro_seconds},"
            f"afade=t=out:st={total_duration - outro_seconds}:d={outro_seconds},"
            f"volume='{vol_expr}':eval=frame[music];"
            f"[0:a]adelay={intro_ms}|{intro_ms},asetpts=PTS-STARTPTS[voice];"
            f"[music][voice]amix=inputs=2:duration=first:"
            f"dropout_transition={outro_seconds}[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(vo_path),
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ac", "2",
            "-ar", "44100",
            "-b:a", "192k",
            str(output_path),
        ]

        logger.info("Mixing audio via FFmpeg...")
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            raise MixingError(f"FFmpeg mixing failed: {exc.stderr}") from exc

        final_bytes = output_path.read_bytes()
        logger.info("Mixed audio: %d bytes", len(final_bytes))
        return final_bytes, stretch_factor
