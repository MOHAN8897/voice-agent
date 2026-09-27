"""WAV → MP3 for call recording downloads."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from server.utils.logger import logger


def convert_wav_to_mp3(
    wav_path: Path,
    mp3_path: Path,
    *,
    bitrate: str = "128k",
    timeout_sec: int = 120,
) -> bool:
    """Encode mono/stereo WAV to MP3 via ffmpeg. Returns False if ffmpeg is missing."""
    wav = Path(wav_path)
    mp3 = Path(mp3_path)
    if not wav.is_file() or wav.stat().st_size < 44:
        return False
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("[AUDIO] ffmpeg not found — MP3 download unavailable")
        return False
    mp3.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(wav),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                str(mp3),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_sec,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("[AUDIO] wav→mp3 failed %s: %s", wav.name, str(exc)[:200])
        return False
    return mp3.is_file() and mp3.stat().st_size > 0
