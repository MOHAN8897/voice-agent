"""Object C — token budget and rolling-summary singularity."""
from __future__ import annotations

from server.call.memory_projection import build


def test_projection_priority_and_slots():
    text = build(
        {
            "facts": {"name": "Ravi", "city": "Hyderabad"},
            "preferences": {"language": "te-en mix"},
            "important_context": "Prefers Gachibowli.",
            "summary": "Caller looking for 2BHK.",
        },
        include_summary=False,
        max_tokens=150,
    )
    assert "[Facts]" in text
    assert "Ravi" in text
    assert "[Preferences]" in text
    assert "[Summary]" not in text


def test_projection_includes_summary_when_no_separate_block():
    text = build(
        {
            "facts": {"name": "Ravi"},
            "preferences": {},
            "important_context": "",
            "summary": "Caller Ravi asked about flats.",
        },
        include_summary=True,
        max_tokens=150,
    )
    assert "[Summary]" in text
    assert "flats" in text


def test_projection_truncates_to_budget():
    long_facts = {f"k{i}": "x" * 40 for i in range(20)}
    text = build(
        {
            "facts": long_facts,
            "preferences": {"p": "yyyyyyyyyyyyyyyyyyyy"},
            "important_context": "context " * 40,
            "summary": "summary " * 40,
        },
        include_summary=True,
        max_tokens=50,
    )
    from server.agent.brain_prompt_composer import estimate_tokens

    assert estimate_tokens(text) <= 55
    assert "[Facts]" in text


def test_empty_snapshot_renders_empty():
    assert build({}, include_summary=True) == ""
