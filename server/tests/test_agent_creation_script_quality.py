"""Regression tests for the agent-creation fixes.

Three separate defects surfaced from one reported flow:
  1. `--- ENTITY TAGS ---` leaked into the script the customer reads and edits.
  2. An English agent's canonical opening came back in Hindi/Tanglish.
  3. The generated script was too thin to brief a real caller.
Plus the client-side token race that made Phone & voice fail with "Invalid or
expired token".
"""
from __future__ import annotations

import re

import pytest

from server.agent.brain_prompt_composer import estimate_tokens
from server.brain.agent_script_compiler import (
    _generated_opening_allowed,
    _opening_line_is_language_compatible,
    compile_agent_from_brief,
)
from server.brain.script_entities import parse_entity_tags, strip_entity_tags_section

SPANDANA_BRIEF = (
    "agent name is mohan, business name is spandana junior college, the agent should call "
    "parents to join their children in our college. we are providing low fees and also "
    "providing coaching for iit and jee main from the start of the college"
)


def _opening_of(script: str) -> str:
    if "--- CANONICAL OPENING ---" not in script:
        return ""
    return script.split("--- CANONICAL OPENING ---", 1)[1].split("\n---", 1)[0]


# --- 1. Entity tags must not be part of the user-visible script -----------------


@pytest.mark.asyncio
async def test_compiled_script_carries_entity_tags_the_runtime_needs():
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    tags = parse_entity_tags(result.agent_script)
    assert tags.get("agent_name") == "Mohan"
    assert tags.get("role") == "education"
    # The runtime pins the opening line from these, so they must survive compilation.
    assert tags.get("opening_line")


@pytest.mark.asyncio
async def test_entity_tags_are_stripped_from_the_script_a_person_reads():
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    visible = strip_entity_tags_section(result.agent_script)
    assert "ENTITY TAGS" not in visible
    assert "@agent_name" not in visible
    # Stripping is display-only: the business content is still there.
    assert "Mohan" in visible
    assert "spandana junior college" in visible.lower()


# --- 2. An English agent must not open in another language ---------------------


@pytest.mark.parametrize(
    "leaked",
    [
        "Namaste, main Mohan bol raha hoon Spandana Junior College se.",
        "Namaste, main Mohan bol raha hoon Spandana Junior College se. Kya aap free hain?",
        "Hi, nenu Mohan, Spandana Junior College nunchi matladutunnanu. Meeru free unnara?",
        "नमस्ते, मैं मोहन बोल रहा हूँ।",
    ],
)
def test_wrong_language_openings_are_rejected_for_english_locales(leaked: str):
    assert not _opening_line_is_language_compatible(leaked, "en-IN")
    assert not _opening_line_is_language_compatible(leaked, "en-US")


@pytest.mark.parametrize(
    "good",
    [
        "Hi, this is Mohan calling from Spandana Junior College. Do you have a moment?",
        "Hello, my name is Priya from Acme Realty. How can I help you today?",
    ],
)
def test_english_openings_are_accepted_for_english_locales(good: str):
    assert _opening_line_is_language_compatible(good, "en-IN")
    assert _opening_line_is_language_compatible(good, "en-US")


def test_indic_locales_keep_their_own_script_in_the_opening():
    tanglish = "Hi, nenu Mohan, Spandana Junior College nundi matladutunnanu. Meeru free unnara?"
    assert _opening_line_is_language_compatible(tanglish, "te-IN")
    assert _opening_line_is_language_compatible(
        "नमस्ते, मैं मोहन बोल रही हूँ।", "hi-IN"
    )


def test_english_locales_never_take_the_interpreters_opening():
    """The drift was different every compile, so it cannot be pattern-matched."""
    assert _generated_opening_allowed("en-IN") is False
    assert _generated_opening_allowed("en-US") is False
    assert _generated_opening_allowed("te-IN") is True


@pytest.mark.asyncio
async def test_english_agent_opens_in_english():
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    opening = _opening_of(result.agent_script)
    assert opening, "no canonical opening in the script"
    assert not any("\u0900" <= ch <= "\u0dff" for ch in opening), opening
    assert not any("\u0c00" <= ch <= "\u0c7f" for ch in opening), opening
    assert "mohan" in opening.lower()
    assert "spandana junior college" in opening.lower()


@pytest.mark.asyncio
async def test_opening_is_never_cut_mid_word():
    """A truncated greeting used to end "...call kar rah" and get spoken aloud."""
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    opening = _opening_of(result.agent_script).strip()
    assert opening
    assert opening.rstrip().endswith(("?", ".", "!")), opening


# --- 3. The script has to actually brief a caller ------------------------------


@pytest.mark.asyncio
async def test_generated_script_is_descriptive_enough_to_use():
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    visible = strip_entity_tags_section(result.agent_script)
    tokens = estimate_tokens(visible)
    # The reported script was ~369 tokens and too thin to brief a real caller.
    assert tokens >= 550, f"script only {tokens} tokens"

    for section in (
        "AGENT IDENTITY",
        "COMPANY & OFFER",
        "CANONICAL OPENING",
        "YOUR ROLE ON THIS CALL",
        "HOW THE CALL SHOULD GO",
        "WHEN YOU DO NOT KNOW SOMETHING",
        "WHAT TO REMEMBER BEFORE YOU CLOSE",
    ):
        assert section in visible, f"missing {section}"


@pytest.mark.asyncio
async def test_expanded_script_stays_inside_the_brain_budget():
    from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS

    _compiled, _result, _raw, compiled_tokens, _budget = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    assert compiled_tokens <= BUDGET_MAX_TOKENS


@pytest.mark.asyncio
async def test_expanded_script_invents_no_prices():
    """The brief names no fees, so the expansion must not manufacture any."""
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    visible = strip_entity_tags_section(result.agent_script).lower()
    # Word-boundary checks: "yours." is not an invented "Rs." price.
    for invented in ("₹", "rupees", "lakh", "crore", "discount of", "rs.", "inr"):
        assert not re.search(rf"(?<![a-z]){re.escape(invented)}(?![a-z])", visible), (
            f"invented {invented!r}"
        )
    assert not re.search(r"\d+\s*%", visible), "invented a percentage"


@pytest.mark.asyncio
async def test_expanded_script_stays_in_english():
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=SPANDANA_BRIEF, language="en-IN", use_llm=False
    )
    visible = strip_entity_tags_section(result.agent_script)
    for name, lo, hi in (
        ("devanagari", "\u0900", "\u097f"),
        ("telugu", "\u0c00", "\u0c7f"),
        ("tamil", "\u0b80", "\u0bff"),
        ("kannada", "\u0c80", "\u0cff"),
    ):
        assert not any(lo <= ch <= hi for ch in visible), f"{name} script in the user script"