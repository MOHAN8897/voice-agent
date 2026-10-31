import pytest

from server.brain.agent_spec import AgentSpec, Evidenced
from server.brain.agent_spec_script_builder import (
    generate_deterministic_script_from_spec,
    lint_agent_script,
)


def test_generate_script_from_user_case_spec():
    spec = AgentSpec(
        language_code="en-IN",
        agent_name=Evidenced(value="Sindhuja", confidence=0.9),
        company_name=Evidenced(value="Mohan Private Limited", confidence=0.9),
        location=Evidenced(value="Vanasthalipuram, Hyderabad", confidence=0.9),
        offering=Evidenced(value="flats and plots", confidence=0.9),
        call_objective=Evidenced(value="book a site visit", confidence=0.9),
        qualification_questions=["interested project", "budget", "preferred configuration"],
    )

    script = generate_deterministic_script_from_spec(spec, direction="outbound")

    assert "You are Sindhuja, representing Mohan Private Limited" in script
    assert "Hi, this is Sindhuja calling from Mohan Private Limited" in script
    assert "flats and plots" in script
    assert "Vanasthalipuram, Hyderabad" in script
    assert "book a site visit" in script
    assert "Priya" not in script
    assert "Alex" not in script

    # Linter passes clean
    issues = lint_agent_script(script, spec)
    assert issues == []


def test_linter_catches_legacy_default_priya():
    spec = AgentSpec(
        language_code="en-IN",
        agent_name=Evidenced(value="Sindhuja"),
        company_name=Evidenced(value="Mohan Private Limited"),
    )
    bad_script = (
        "--- AGENT IDENTITY ---\nYou are Priya, representing Mohan Private Limited.\n\n"
        "--- CANONICAL OPENING ---\nHi, this is Priya calling."
    )
    issues = lint_agent_script(bad_script, spec)
    assert any("Forbidden legacy default name 'priya'" in issue for issue in issues)
    assert any("Missing required agent name 'Sindhuja'" in issue for issue in issues)


def test_linter_allows_runtime_tags_rejects_unresolved_placeholders():
    spec = AgentSpec(
        language_code="en-IN",
        agent_name=Evidenced(value="Sindhuja"),
        company_name=Evidenced(value="Mohan Private Limited"),
    )
    clean_script = generate_deterministic_script_from_spec(spec)
    assert lint_agent_script(clean_script, spec) == []

    broken_script = clean_script + "\nRemember {{unresolved_token}}."
    issues = lint_agent_script(broken_script, spec)
    assert any("Unresolved template placeholder '{{unresolved_token}}'" in issue for issue in issues)


def test_linter_checks_recording_disclosure():
    spec = AgentSpec(
        language_code="en-IN",
        agent_name=Evidenced(value="Sindhuja"),
        company_name=Evidenced(value="Mohan Private Limited"),
    )
    script_without_disclosure = generate_deterministic_script_from_spec(
        spec, recording_disclosure_enabled=False
    )
    issues = lint_agent_script(
        script_without_disclosure, spec, recording_disclosure_enabled=True
    )
    assert any("Recording disclosure required" in issue for issue in issues)

    script_with_disclosure = generate_deterministic_script_from_spec(
        spec, recording_disclosure_enabled=True
    )
    issues_clean = lint_agent_script(
        script_with_disclosure, spec, recording_disclosure_enabled=True
    )
    assert issues_clean == []
