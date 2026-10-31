"""WAV → MP3 & MP4 transcoding for call recording playback and downloads."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from server.utils.logger import logger


def _pyav_transcode(src_wav: Path, dest_path: Path, *, codec_name: str, format_name: str, bitrate: str = "128k") -> bool:
    """Encode WAV to target audio format using PyAV without external ffmpeg binary."""
    try:
        import av

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
        with av.open(str(src_wav), mode="r") as in_container:
            if not in_container.streams.audio:
                return False
            in_stream = in_container.streams.audio[0]
            with av.open(str(tmp_dest), mode="w", format=format_name) as out_container:
                out_stream = out_container.add_stream(codec_name, rate=in_stream.rate)
                try:
                    out_stream.bit_rate = int(bitrate.rstrip("kK")) * 1000
                except Exception:
                    pass
                # WAVs written by the wave module carry no channel mask ("2 channels"),
                # which LAME and AAC reject; name the layout from the channel count.
                out_stream.layout = "stereo" if in_stream.channels >= 2 else "mono"
                for frame in in_container.decode(in_stream):
                    frame.pts = None
                    for packet in out_stream.encode(frame):
                        out_container.mux(packet)
                for packet in out_stream.encode(None):
                    out_container.mux(packet)
        if tmp_dest.is_file() and tmp_dest.stat().st_size > 0:
            tmp_dest.replace(dest_path)
            return True
        if tmp_dest.exists():
            tmp_dest.unlink(missing_ok=True)
        return False
    except Exception as exc:
        logger.warning("[AUDIO] PyAV transcode failed for %s → %s: %s", src_wav.name, dest_path.name, str(exc)[:200])
        tmp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
        if tmp_dest.exists():
            tmp_dest.unlink(missing_ok=True)
        return False


def convert_wav_to_mp3(
    wav_path: Path,
    mp3_path: Path,
    *,
    bitrate: str = "128k",
    timeout_sec: int = 120,
) -> bool:
    """Encode mono/stereo WAV to MP3 via PyAV or ffmpeg fallback."""
    wav = Path(wav_path)
    mp3 = Path(mp3_path)
    if not wav.is_file() or wav.stat().st_size < 44:
        return False

    # Try PyAV first (in-process, fast, no external process)
    if _pyav_transcode(wav, mp3, codec_name="mp3", format_name="mp3", bitrate=bitrate):
        return True

    # Fallback to ffmpeg CLI if installed
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("[AUDIO] ffmpeg and PyAV MP3 encoding unavailable")
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


def convert_wav_to_mp4(
    wav_path: Path,
    mp4_path: Path,
    *,
    bitrate: str = "128k",
    timeout_sec: int = 120,
) -> bool:
    """Encode mono/stereo WAV to MP4 (AAC audio container) via PyAV or ffmpeg."""
    wav = Path(wav_path)
    mp4 = Path(mp4_path)
    if not wav.is_file() or wav.stat().st_size < 44:
        return False

    # Try PyAV first (in-process, fast, AAC audio in MP4 container)
    if _pyav_transcode(wav, mp4, codec_name="aac", format_name="mp4", bitrate=bitrate):
        return True

    # Fallback to ffmpeg CLI if installed
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("[AUDIO] ffmpeg and PyAV MP4 encoding unavailable")
        return False
    mp4.parent.mkdir(parents=True, exist_ok=True)
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
                "aac",
                "-b:a",
                bitrate,
                str(mp4),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_sec,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("[AUDIO] wav→mp4 failed %s: %s", wav.name, str(exc)[:200])
        return False
    return mp4.is_file() and mp4.stat().st_size > 0
