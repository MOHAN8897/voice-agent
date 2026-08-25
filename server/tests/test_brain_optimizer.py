"""Brain optimizer tests — Phase 2."""
import pytest

from server.brain.business_prompt_optimizer import optimize_business_prompt


@pytest.mark.asyncio
async def test_optimizer_preserves_delimiters(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    raw = "<!-- section:facts:1 -->\nWe sell plots.\n\n<!-- section:faq:2 -->\n"
    result = await optimize_business_prompt(raw, source_checksum="abc")
    assert "<!-- section:facts:1 -->" in result.optimized_business_prompt
    assert "We sell plots." in result.optimized_business_prompt
    assert result.source_checksum == "abc"
