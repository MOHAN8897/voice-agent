"""Live-stack language aliases (en-US / eng / en-GB) must resolve, not crash PSTN start."""
from __future__ import annotations

import inspect

import pytest

from server.config.constants import (
    coerce_supported_language,
    language_in_supported,
    normalize_supported_language,
    provider_language_code,
)
from server.config.env import Settings
from server.prompts.agent_voice_rules import normalize_compile_language
from server.providers.registry import ProviderRegistry
from server.providers.resolver import StackResolver
from server.utils.errors import AppError, ErrorCode


@pytest.fixture
def resolver(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("ENABLE_SARVAM", "true")
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    return StackResolver(settings, registry)


def test_normalize_english_aliases():
    assert normalize_supported_language("en-US") == "en-US"
    assert normalize_supported_language("en-us") == "en-US"
    assert normalize_supported_language("en_US") == "en-US"
    assert normalize_supported_language("en-gb") == "en-US"
    assert normalize_supported_language("en-GB") == "en-US"
    assert normalize_supported_language("eng") == "en-IN"
    assert normalize_supported_language("english") == "en-IN"
    assert normalize_supported_language("en") == "en-IN"
    assert normalize_supported_language("te") == "te-IN"
    assert normalize_supported_language("hi_in") == "hi-IN"
    assert language_in_supported("en-US")
    assert language_in_supported("en-us")
    assert not language_in_supported("fr-FR")
    assert coerce_supported_language("fr-FR") == "te-IN"


def test_sarvam_provider_code_maps_en_us_to_en_in():
    assert provider_language_code("en-US", provider="sarvam", stage="stt") == "en-IN"
    assert provider_language_code("en-US", provider="sarvam", stage="tts") == "en-IN"
    assert provider_language_code("en-US", provider="cartesia", stage="stt") == "en"


def test_compile_language_keeps_spoken_packs():
    assert normalize_compile_language("en-US") == "en-US"
    assert normalize_compile_language("en-gb") == "en-US"
    assert normalize_compile_language("eng") == "en-IN"


def test_resolver_accepts_en_us_and_aliases(resolver):
    for code in ("en-US", "en-us", "en-GB", "eng"):
        stack = resolver.resolve(mode="env", tier="medium", language=code)
        assert stack.language in ("en-US", "en-IN")
        if code.lower() in ("en-us", "en-gb") or code == "en-US":
            assert stack.language == "en-US"
        if code == "eng":
            assert stack.language == "en-IN"


def test_resolver_still_rejects_unknown_language(resolver):
    with pytest.raises(AppError) as exc:
        resolver.resolve(mode="env", tier="medium", language="fr-FR")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR
    assert "not supported" in str(exc.value)


def test_stream_start_failure_closes_ws_without_reraise():
    from server.services.telnyx_pstn_bridge import TelnyxPstnBridge

    src = inspect.getsource(TelnyxPstnBridge._on_start)
    fail = src.split("except Exception as exc:")[-1]
    assert "self._closed = True" in fail
    assert "ws.close" in fail
    assert fail.strip().endswith("return")
    assert "raise" not in fail


@pytest.mark.asyncio
async def test_telnyx_hangup_treats_422_as_already_ended():
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    client = TelnyxClient(cfg={"api_key": "t", "connection_id": "c", "phone_number": "+15551234567"})

    async def boom(*_a, **_k):
        raise TelnyxApiError("Telnyx API 422", status=422, body="call already ended")

    client._request = boom  # type: ignore[method-assign]
    assert await client.hangup("v3:already-gone") == {}
