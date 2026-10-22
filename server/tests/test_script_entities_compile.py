import pytest

from server.brain.agent_script_compiler import compile_agent_from_brief
from server.brain.script_entities import parse_entity_tags


@pytest.mark.asyncio
async def test_compile_agent_from_brief_includes_entity_tags():
    brief = (
        "Create an English sales agent named Priya for Acme Realty. "
        "Known listing: 2BHK from fifty lakhs."
    )
    _compiled, result, *_ = await compile_agent_from_brief(
        brief=brief,
        language="en-IN",
        use_llm=False,
        interpret_brief=False,
        direction="outbound",
    )
    tags = parse_entity_tags(result.agent_script)
    assert tags.get("agent_name") == "Priya"
    assert tags.get("company_name") == "Acme Realty"
    assert "@agent_name:" in result.agent_script
    assert tags.get("opening_line")
