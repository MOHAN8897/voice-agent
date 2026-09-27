from server.brain.script_entities import (
    build_script_entities,
    format_entity_tags_section,
    parse_entity_tags,
    strip_entity_tags_section,
    with_entity_tags_section,
)


def test_format_and_parse_entity_tags():
    entities = build_script_entities(
        agent_name="Priya",
        company_name="Acme Realty",
        work_scope="2BHK sales",
        role="sales",
        language="te-IN",
        direction="outbound",
        opening_line="Hi, nenu Priya, Acme nundi. Time unda?",
    )
    section = format_entity_tags_section(entities)
    assert "@agent_name: Priya" in section
    assert "@company_name: Acme Realty" in section
    parsed = parse_entity_tags(section)
    assert parsed["agent_name"] == "Priya"
    assert parsed["opening_line"].startswith("Hi,")


def test_with_entity_tags_prepends_without_dropping_body():
    body = "--- AGENT IDENTITY ---\nYou are Priya.\n"
    entities = build_script_entities(agent_name="Priya", company_name="Co")
    merged = with_entity_tags_section(body, entities)
    assert merged.startswith("--- ENTITY TAGS ---")
    assert "--- AGENT IDENTITY ---" in merged
    assert strip_entity_tags_section(merged).strip() == body.strip()
