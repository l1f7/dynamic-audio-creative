"""Validate and normalise pushed audio before it is registered as a run."""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MP3_FORMAT_NAME = "mp3"
MP3_BITRATE = "192k"
DURATION_TOLERANCE_SECONDS = 1.0
PROBE_TIMEOUT_SECONDS = 30
TRANSCODE_TIMEOUT_SECONDS = 120


class PushRejected(Exception):
    """The file itself is wrong. Maps to HTTP 422; the message is shown to the user."""


class ProbedAudio:
    def __init__(self, format_name: str, duration: float):
        self.format_name = format_name
        self.duration = duration

    @property
    def is_mp3(self) -> bool:
        return MP3_FORMAT_NAME in self.format_name.split(",")


def probe(audio_bytes: bytes, filename: str) -> ProbedAudio:
    """Read container format and duration with ffprobe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / _safe_name(filename)
        path.write_bytes(audio_bytes)
        output = _run_ffprobe(path)
    return _parse_probe_output(output)


def check_duration(probed: ProbedAudio, target_seconds: float | None) -> None:
    if target_seconds is None:
        return
    if abs(probed.duration - target_seconds) > DURATION_TOLERANCE_SECONDS:
        raise PushRejected(
            f"Audio is {probed.duration:.1f}s but the ad unit expects {target_seconds:g}s"
        )


def transcode_to_mp3(audio_bytes: bytes, filename: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / _safe_name(filename)
        dst = Path(tmpdir) / "out.mp3"
        src.write_bytes(audio_bytes)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-b:a", MP3_BITRATE, str(dst)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True,
                           timeout=TRANSCODE_TIMEOUT_SECONDS)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise PushRejected(f"Could not convert audio to MP3: {exc}") from exc
        return dst.read_bytes()


def _run_ffprobe(path: Path) -> str:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=format_name,duration",
        "-of", "default=noprint_wrappers=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True,
                                timeout=PROBE_TIMEOUT_SECONDS)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PushRejected("Unsupported or unreadable audio format") from exc
    return result.stdout


def _parse_probe_output(output: str) -> ProbedAudio:
    fields = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    try:
        return ProbedAudio(fields["format_name"], float(fields["duration"]))
    except (KeyError, ValueError) as exc:
        raise PushRejected("Could not determine audio duration") from exc


def _safe_name(filename: str) -> str:
    suffix = Path(filename).suffix[:8] or ".bin"
    return f"pushed{suffix}"
