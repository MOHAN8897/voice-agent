"""Disclosure injection must reach both compiled-brain shapes and stay idempotent."""
from __future__ import annotations

import pytest

from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.prompts.agent_voice_rules import (
    inject_recording_disclosure,
    strip_recording_disclosure,
)

MARKER = "RECORDING DISCLOSURE POLICY"


def test_injection_is_idempotent_and_replaces_the_meaning_text():
    first = inject_recording_disclosure(
        "--- CALLING SCRIPT ---\nSay hello.\n\n--- SAFETY ---\nNever invent facts.",
        enabled=True,
        disclosure_text="First notice: calls are recorded.",
        language="en-IN",
    )
    second = inject_recording_disclosure(
        first,
        enabled=True,
        disclosure_text="Second notice: calls are recorded.",
        language="en-IN",
    )
    assert second.count(MARKER) == 1
    assert "Second notice: calls are recorded." in second
    assert "First notice: calls are recorded." not in second
    assert second.index(MARKER) < second.index("--- SAFETY ---")


def test_disabling_removes_an_existing_block():
    enabled = inject_recording_disclosure(
        "--- SAFETY ---\nNever invent facts.",
        enabled=True,
        disclosure_text="Calls are recorded.",
        language="en-IN",
    )
    disabled = inject_recording_disclosure(
        enabled,
        enabled=False,
        disclosure_text=None,
        language="en-IN",
    )
    assert MARKER not in disabled
    assert "--- SAFETY ---" in disabled


def test_strip_leaves_unrelated_sections_alone():
    text = (
        "--- CALLING SCRIPT ---\nSay hello.\n\n"
        "### RECORDING DISCLOSURE POLICY (NATURAL, ONCE):\n"
        "- Deliver this during your first substantive reply.\n\n"
        "--- SAFETY ---\nNever invent facts."
    )
    stripped = strip_recording_disclosure(text)
    assert MARKER not in stripped
    assert "Say hello." in stripped
    assert "--- SAFETY ---" in stripped


@pytest.mark.asyncio
async def test_publish_and_compile_keep_disclosure_in_exact_artifact(monkeypatch):
    from server.brain.agent_service import agent_service
    from server.brain.compiled_brain_service import compiled_brain_service

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()
    agent = await agent_service.ensure_default_agent()
    from server.brain.business_brain_store import business_brain_store

    await business_brain_store.ensure_default_sections(agent["agent_id"])

    async def disclosure_enabled(_agent_id: str):
        return "en-IN", True, "Calls may be recorded for quality."

    monkeypatch.setattr(compiled_brain_service, "_agent_info", disclosure_enabled)
    unified = assemble_unified_brain(
        language="en-IN",
        script="--- AGENT IDENTITY ---\nYou are Sam from Acme.",
    )
    published = await compiled_brain_service.publish_agent_brain(
        agent["agent_id"], optimized_prompt=unified,
    )
    assert published["compiled_text"].count(MARKER) == 1
    assert "Calls may be recorded for quality." in published["compiled_text"]

    # The exact-artifact compile path must re-apply the current setting instead
    # of returning the stored artifact untouched.
    compiled = await compiled_brain_service.compile_for_agent(agent["agent_id"])
    assert compiled["compiled_text"].count(MARKER) == 1
    assert "Calls may be recorded for quality." in compiled["compiled_text"]
    get_settings.cache_clear()
