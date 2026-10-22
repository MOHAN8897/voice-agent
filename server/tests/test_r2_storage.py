"""Unit tests for Cloudflare R2 object storage service."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from server.services.r2_storage import R2StorageService


@pytest.fixture
def mock_r2_settings():
    with patch("server.services.r2_storage.get_settings") as mock_settings:
        s = MagicMock()
        s.r2_account_id = "test-account-id"
        s.r2_access_key_id = "test-key-id"
        s.r2_secret_access_key = "test-secret-key"
        s.r2_bucket_name = "test-bucket"
        mock_settings.return_value = s
        yield s


@pytest.fixture
def mock_unconfigured_settings():
    with patch("server.services.r2_storage.get_settings") as mock_settings:
        s = MagicMock()
        s.r2_account_id = None
        s.r2_access_key_id = None
        s.r2_secret_access_key = None
        s.r2_bucket_name = "test-bucket"
        mock_settings.return_value = s
        yield s


def test_is_configured_true(mock_r2_settings):
    svc = R2StorageService()
    assert svc.is_configured() is True


def test_is_configured_false(mock_unconfigured_settings):
    svc = R2StorageService()
    assert svc.is_configured() is False


@pytest.mark.asyncio
async def test_upload_unconfigured_returns_none(mock_unconfigured_settings):
    svc = R2StorageService()
    result = await svc.upload_bytes("calls/test/file.wav", b"fake-data")
    assert result is None
    presigned = await svc.presigned_url("calls/test/file.wav")
    assert presigned is None


@pytest.mark.asyncio
async def test_upload_bytes_success(mock_r2_settings):
    svc = R2StorageService()
    mock_s3 = AsyncMock()
    mock_s3.put_object = AsyncMock()
    mock_s3.head_object = AsyncMock(return_value={"ContentLength": 9})

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_s3
    mock_client_ctx.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        res = await svc.upload_bytes("test-key", b"123456789")
        assert res == "test-key"
        mock_s3.put_object.assert_called_once()
        mock_s3.head_object.assert_called_once_with(Bucket="test-bucket", Key="test-key")


@pytest.mark.asyncio
async def test_upload_audio_file(mock_r2_settings, tmp_path: Path):
    svc = R2StorageService()
    test_file = tmp_path / "audio.wav"
    test_file.write_bytes(b"RIFF....WAVEfmt ")

    mock_s3 = AsyncMock()
    mock_s3.put_object = AsyncMock()
    mock_s3.head_object = AsyncMock(return_value={"ContentLength": len(test_file.read_bytes())})

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_s3
    mock_client_ctx.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        res = await svc.upload_audio_file("call-123", test_file, fmt="wav")
        assert res == "calls/call-123/recording.wav"


@pytest.mark.asyncio
async def test_presigned_url(mock_r2_settings):
    svc = R2StorageService()
    mock_s3 = AsyncMock()
    mock_s3.generate_presigned_url = AsyncMock(return_value="https://r2.test/download-link")

    mock_client_ctx = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_s3
    mock_client_ctx.__aexit__.return_value = None

    mock_session = MagicMock()
    mock_session.client.return_value = mock_client_ctx

    mock_aioboto3 = MagicMock()
    mock_aioboto3.Session.return_value = mock_session

    with patch.dict(sys.modules, {"aioboto3": mock_aioboto3}):
        url = await svc.presigned_url("calls/call-123/recording.wav")
        assert url == "https://r2.test/download-link"
