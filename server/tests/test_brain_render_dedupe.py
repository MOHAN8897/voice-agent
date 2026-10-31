"""A published brain renders with one copy of each platform rule.

Call 35002575 ran on a brain frozen before the guardrail duplicates were removed
from the compiler; rendering must clean those too, not only fresh compiles.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.brain.compiled_brain_artifact import canonicalize_platform_rules, refresh_platform_sections

CALL_META = Path(__file__).resolve().parents[2] / "data" / "calls" / "35002575-2555-4b96-9058-6d345942a13d" / "meta.json"

STALE_GUARDRAILS = """--- GUARDRAILS ---
- -- GUARDRAILS ---
- Never invent prices, availability, or policies.
- Never greet twice in one call.
- Never claim to be anyone except Meera.
- Follow the selected primary language with natural English mixing.
- Speak naturally as the named AI assistant; answer honestly if asked whether you are AI.
- Do not talk continuously — end each turn when the point is made.
"""


def test_stale_duplicate_guardrail_lines_are_dropped_and_unique_ones_kept():
    out = canonicalize_platform_rules(STALE_GUARDRAILS)
    for line in (
        "Never invent prices, availability, or policies.",
        "Never greet twice in one call.",
        "Follow the selected primary language",
        "answer honestly if asked whether you are AI",
        "Do not talk continuously",
    ):
        assert line not in out
    assert "- Never claim to be anyone except Meera." in out


@pytest.mark.skipif(not CALL_META.exists(), reason="call evidence not present in this checkout")
def test_call_35002575_brain_renders_without_duplicate_rules():
    brain = json.loads(CALL_META.read_text(encoding="utf-8"))["compiled_brain_text"]
    out = canonicalize_platform_rules(refresh_platform_sections(brain, "te-IN"))
    assert out.count("--- SPOKEN LANGUAGE (te-IN) ---") == 1
    assert out.count("CONVERSATIONAL REGISTER") == 1
    assert out.count("answer honestly") == 1
    assert "Do not invent callbacks" not in out
    assert "do not assume a callback is allowed" not in out
    assert "After the callee speaks, say once" not in out
    assert len(out) < len(brain)
