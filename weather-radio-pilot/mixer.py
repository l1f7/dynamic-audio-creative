"""Mix voiceover with background music bed using FFmpeg."""

import os
import subprocess
import sys


def mix_audio(
    music_bed_path: str,
    voiceover_path: str,
    final_ad_path: str,
    output_dir: str,
    intro_seconds: float = 2.0,
    outro_seconds: float = 2.0,
    duck_volume: float = 0.2,
    duck_fade: float = 0.5,
) -> str:
    """Mix voiceover with a music bed and write the final ad MP3.

    Args:
        music_bed_path: Path to the background music MP3.
        voiceover_path: Path to the voiceover MP3.
        final_ad_path: Path for the output mixed ad.
        output_dir: Directory to ensure exists for output.
        intro_seconds: Music plays at full volume before voice starts.
        outro_seconds: Music fades back up then out after voice ends.
        duck_volume: Music volume during voiceover (0.0–1.0).
        duck_fade: Seconds to ramp between full and ducked volume.

    Returns:
        Path to the final mixed ad.
    """
    # Pre-flight checks
    if not os.path.isfile(music_bed_path):
        print(
            f"ERROR: Music bed not found at {music_bed_path}\n"
            "       Place a background music MP3 there before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not os.path.isfile(voiceover_path):
        print(
            f"ERROR: Voiceover not found at {voiceover_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print("Mixing with music bed via FFmpeg...")

    # Get voiceover duration so we can time the music envelope
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        voiceover_path,
    ]
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        vo_duration = float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERROR: Could not determine voiceover duration: {exc}", file=sys.stderr)
        sys.exit(1)

    # Total ad duration: intro + voiceover + outro
    total_duration = intro_seconds + vo_duration + outro_seconds
    intro_ms = int(intro_seconds * 1000)

    # Ducking envelope timestamps
    duck_start = intro_seconds           # voice begins, start ducking
    duck_end = intro_seconds + vo_duration  # voice ends, start recovering
    dv = duck_volume
    df = duck_fade

    # Volume expression with smooth ramps:
    #   - Before duck_start: full volume (1.0)
    #   - duck_start to duck_start+fade: ramp 1.0 → duck_volume
    #   - During voiceover: hold at duck_volume
    #   - duck_end to duck_end+fade: ramp duck_volume → 1.0
    #   - After recovery: full volume (1.0)
    vol_expr = (
        f"if(lt(t,{duck_start}),1,"
        f"if(lt(t,{duck_start + df}),1-(1-{dv})*(t-{duck_start})/{df},"
        f"if(lt(t,{duck_end}),{dv},"
        f"if(lt(t,{duck_end + df}),{dv}+(1-{dv})*(t-{duck_end})/{df},"
        f"1))))"
    )

    # Filter graph:
    # 1. Trim music bed to total duration, fade in over intro, fade out over outro
    # 2. Smooth volume ducking during voiceover with configurable ramp
    # 3. Delay voiceover by intro duration so music plays alone first
    # 4. Mix the two streams
    filter_complex = (
        f"[1:a]atrim=0:{total_duration},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={intro_seconds},"
        f"afade=t=out:st={total_duration - outro_seconds}:d={outro_seconds},"
        f"volume='{vol_expr}':eval=frame[music];"
        f"[0:a]adelay={intro_ms}|{intro_ms},asetpts=PTS-STARTPTS[voice];"
        f"[music][voice]amix=inputs=2:duration=first:dropout_transition={outro_seconds}[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", voiceover_path,
        "-i", music_bed_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ac", "2",
        "-ar", "44100",
        "-b:a", "192k",
        final_ad_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: FFmpeg mixing failed:\n{exc.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Final ad saved to {final_ad_path}")
    return final_ad_path
