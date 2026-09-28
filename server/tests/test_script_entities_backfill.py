from server.brain.script_entities import (
    backfill_entity_tags_in_script,
    parse_entity_tags,
    realign_compiled_brain_for_session,
)


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


def test_backfill_syncs_language_tag_to_session_language():
    script = (
        "--- ENTITY TAGS ---\n"
        "Machine-readable call entities (do not remove — used for voice opening and brain pins).\n"
        "@agent_name: Alex\n"
        "@company_name: Acme\n"
        "@language: en-US\n"
        "@direction: outbound\n"
        "--- AGENT IDENTITY ---\n"
        "You are Alex.\n"
    )
    out = backfill_entity_tags_in_script(script, language="te-IN", direction="outbound")
    tags = parse_entity_tags(out)
    assert tags.get("language") == "te-IN"


def test_realign_compiled_brain_syncs_calling_script_language():
    compiled = (
        "--- SAFETY ---\nrules\n\n"
        "--- CALLING SCRIPT ---\n"
        "--- ENTITY TAGS ---\n"
        "@agent_name: Alex\n"
        "@company_name: Acme\n"
        "@language: en-US\n"
        "@direction: outbound\n"
        "--- AGENT IDENTITY ---\n"
        "You are Alex.\n\n"
        "--- PLATFORM CALL RULES ---\n"
        "rules\n"
    )
    out = realign_compiled_brain_for_session(compiled, "te-IN", direction="outbound")
    tags = parse_entity_tags(out)
    assert tags.get("language") == "te-IN"
    assert "--- CALLING SCRIPT ---" in out
    assert "--- PLATFORM CALL RULES ---" in out


def test_sync_entity_language_regenerates_opening_when_language_changes():
    script = (
        "--- ENTITY TAGS ---\n"
        "@agent_name: Priya\n"
        "@company_name: Acme Realty\n"
        "@language: en-US\n"
        "@direction: outbound\n"
        "@opening_line: Hi, this is Priya from Acme Realty.\n"
        "--- AGENT IDENTITY ---\n"
        "You are Priya.\n"
    )
    out = backfill_entity_tags_in_script(script, language="te-IN", direction="outbound")
    tags = parse_entity_tags(out)
    assert tags.get("language") == "te-IN"
    assert tags.get("opening_line") and "Priya" in tags["opening_line"]
