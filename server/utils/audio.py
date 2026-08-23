"""
Audio helpers — server/utils/audio.py
"""
from __future__ import annotations


def is_allowed_audio(filename: str, content_type: str) -> bool:
    allowed_ext = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in allowed_ext:
        return True
    # Fallback to MIME
    allowed_mime_prefix = ("audio/", "video/webm")
    return content_type.startswith(allowed_mime_prefix) or content_type == "application/octet-stream"


def validate_audio_size(data: bytes, max_bytes: int) -> None:
    from server.utils.errors import AppError, ErrorCode

    if len(data) > max_bytes:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Audio too large ({len(data)} bytes). Max {max_bytes} bytes.",
            status_code=413,
        )
    if len(data) < 100:
        raise AppError(ErrorCode.STT_EMPTY, status_code=400)
