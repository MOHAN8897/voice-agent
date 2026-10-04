"""Cloudflare R2 object storage — zero egress fees, S3-compatible."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.utils.logger import logger


class R2StorageService:
    def __init__(self) -> None:
        pass

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.r2_access_key_id and s.r2_secret_access_key and s.r2_account_id)

    def _client_kwargs(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "service_name": "s3",
            "endpoint_url": f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
            "aws_access_key_id": s.r2_access_key_id,
            "aws_secret_access_key": s.r2_secret_access_key,
            "region_name": "auto",
        }

    async def upload_audio_file(
        self, call_id: str, file_path: str | Path, fmt: str = "wav"
    ) -> str | None:
        """Upload audio from disk, verify receipt, and return storage key."""
        if not self.is_configured():
            return None

        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            logger.warning("[R2] File %s empty or missing for call %s", file_path, call_id)
            return None

        key = f"calls/{call_id}/recording.{fmt}"
        file_bytes = path.read_bytes()

        try:
            import aioboto3
        except ImportError:
            logger.warning("[R2] aioboto3 not installed, skipping audio upload for %s", call_id)
            return None

        try:
            session = aioboto3.Session()
            bucket = get_settings().r2_bucket_name
            content_type = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"

            async with session.client(**self._client_kwargs()) as s3:
                # 1. Put object
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                # 2. Verify existence and byte size
                head = await s3.head_object(Bucket=bucket, Key=key)
                if head.get("ContentLength") != len(file_bytes):
                    raise IOError(
                        f"Uploaded R2 size ({head.get('ContentLength')}) does not match local file size ({len(file_bytes)})"
                    )

            logger.info("[R2] Verified upload for call %s (%d bytes) -> %s", call_id, len(file_bytes), key)
            return key
        except Exception as exc:
            logger.error("[R2] Audio upload failed for call %s: %s", call_id, exc)
            return None

    async def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str | None:
        """Upload raw bytes to R2 and verify receipt."""
        if not self.is_configured() or not data:
            return None

        try:
            import aioboto3
        except ImportError:
            logger.warning("[R2] aioboto3 not installed, skipping upload for %s", key)
            return None

        try:
            session = aioboto3.Session()
            bucket = get_settings().r2_bucket_name
            async with session.client(**self._client_kwargs()) as s3:
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                head = await s3.head_object(Bucket=bucket, Key=key)
                if head.get("ContentLength") != len(data):
                    raise IOError("Uploaded R2 size mismatch")

            logger.info("[R2] Verified upload to %s (%d bytes)", key, len(data))
            return key
        except Exception as exc:
            logger.error("[R2] Upload failed for key %s: %s", key, exc)
            return None

    async def upload_outcome(self, call_id: str, outcome: dict[str, Any]) -> str | None:
        """Upload call outcome JSON to Cloudflare R2."""
        if not self.is_configured():
            return None
        body = json.dumps(outcome, ensure_ascii=False, indent=2).encode("utf-8")
        key = f"calls/{call_id}/outcome.json"
        return await self.upload_bytes(key, body, content_type="application/json")

    async def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a pre-signed download URL for audio playback or export."""
        if not self.is_configured():
            return None

        try:
            import aioboto3
        except ImportError:
            return None

        try:
            session = aioboto3.Session()
            async with session.client(**self._client_kwargs()) as s3:
                return await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": get_settings().r2_bucket_name, "Key": key},
                    ExpiresIn=expires_in,
                )
        except Exception as exc:
            logger.warning("[R2] Presigned URL generation failed for %s: %s", key, exc)
            return None


r2_storage = R2StorageService()
