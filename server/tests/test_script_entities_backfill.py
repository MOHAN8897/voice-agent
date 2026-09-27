from server.brain.script_entities import backfill_entity_tags_in_script, parse_entity_tags


def test_backfill_adds_entity_tags_to_legacy_script():
    script = (
        "--- AGENT IDENTITY ---\n"
        "You are Priya, representing Acme Realty. Always speak as Priya.\n\n"
        "--- COMPANY & OFFER ---\n"
        "Acme Realty. 2BHK from fifty lakhs.\n\n"
        "--- CANONICAL OPENING ---\n"
        "After the callee speaks, say once:\n"
        "Hi, this is Priya calling from Acme Realty. Do you have a moment?\n"
    )
    brief = "Create agent Priya for Acme Realty. Sales outbound."
    out = backfill_entity_tags_in_script(script, brief=brief, language="en-IN", direction="outbound")
    tags = parse_entity_tags(out)
    assert tags.get("agent_name") == "Priya"
    assert "Acme" in (tags.get("company_name") or "")
    assert "@agent_name:" in out
