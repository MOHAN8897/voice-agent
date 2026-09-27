import pytest

from server.brain.agent_script_compiler import (
    compile_agent_from_brief,
    extract_company_from_brief,
)
from server.brain.script_entities import script_conflicts_with_brief

SHEKAR_BRIEF = (
    "agent name is shekar, business name is king private limited whose work is in real estate. "
    "convince the customers for buying the plots in hyderabad at outer ring road area whcih is a "
    "hotspot with high value locations avalable for sale. plot starts at 30 lakhs for 1000 square feet"
)

STALE_AUTO_CARS = (
    "--- ENTITY TAGS ---\n@agent_name: Shekar\n\n"
    "--- AGENT IDENTITY ---\nYou are Priya, representing Auto Cars Private Limited.\n"
)


def test_extract_king_private_limited():
    assert "king" in extract_company_from_brief(SHEKAR_BRIEF).lower()
    assert "limited" in extract_company_from_brief(SHEKAR_BRIEF).lower()


def test_stale_script_detected():
    assert script_conflicts_with_brief(STALE_AUTO_CARS, SHEKAR_BRIEF, language="te-IN")


def test_stale_tags_match_brief_but_body_auto_cars():
    script = (
        "--- ENTITY TAGS ---\n"
        "@agent_name: Shekar\n"
        "@company_name: king private limited\n\n"
        "--- AGENT IDENTITY ---\nYou are Priya, representing Auto Cars Private Limited.\n"
    )
    assert script_conflicts_with_brief(script, SHEKAR_BRIEF, language="te-IN")


@pytest.mark.asyncio
async def test_compile_shekar_brief_no_priya():
    _c, result, *_ = await compile_agent_from_brief(
        brief=SHEKAR_BRIEF,
        language="te-IN",
        use_llm=False,
        interpret_brief=False,
        direction="outbound",
    )
    low = result.agent_script.lower()
    assert "shekar" in low
    assert "priya" not in low
    assert "auto cars" not in low
    assert "king" in low
    assert "30 lakhs" in low or "thirty" in low
