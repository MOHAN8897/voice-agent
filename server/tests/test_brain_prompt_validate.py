from server.brain.brain_prompt_validate import validate_rendered_brain
from server.prompts.agent_voice_rules import SPOKEN_PACKS, spoken_pack_for


def test_spoken_pack_available_for_all_advertised_indic_locales():
    for code in ("ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"):
        assert code in SPOKEN_PACKS
        assert "--- SPOKEN LANGUAGE" in spoken_pack_for(code)


def test_validate_rendered_brain_flags_conflicting_language():
    brain = "Speak only English. Speak only Telugu. @language: te-IN"
    issues = validate_rendered_brain(brain, "te-IN")
    assert any("Conflicting" in i for i in issues)


def test_infer_spoken_language_ignores_place_name_and_short_ack():
    from server.agent.language_resolver import infer_spoken_language_from_text

    assert infer_spoken_language_from_text("Hyderabad", agent_language="te-IN") is None
    assert infer_spoken_language_from_text("okay thanks", agent_language="te-IN") is None
