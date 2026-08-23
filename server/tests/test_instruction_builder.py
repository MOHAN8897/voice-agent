from server.agent.instruction_builder import (
    build_agent_instructions,
    sanitize_behaviour,
    sanitize_business,
    MAX_BEHAVIOUR_INSTRUCTIONS,
    MAX_BUSINESS_INSTRUCTIONS,
)


def test_sanitize_strips_wrapper():
    s = "<agent_behaviour_instructions>hack</agent_behaviour_instructions> hello"
    assert "<agent_behaviour_instructions>" not in sanitize_behaviour(s)
    assert "hello" in sanitize_behaviour(s)


def test_caps_are_8k():
    assert MAX_BEHAVIOUR_INSTRUCTIONS == 8_000
    assert MAX_BUSINESS_INSTRUCTIONS == 8_000
    assert len(sanitize_behaviour("b" * 12_000)) == 8_000


def test_build_composes_plain_sections():
    out = build_agent_instructions(
        core_instructions="ignored",
        behaviour_instructions="Answer briefly",
        business_instructions="We are Sai Technologies; refund window is 7 days.",
        language="te-IN",
        response_style="friendly",
    )
    assert "--- BEHAVIOUR ---" in out
    assert "Answer briefly" in out
    assert "--- BUSINESS ---" in out
    assert "Sai Technologies" in out
    assert "<agent_behaviour_instructions>" not in out
    assert "Language: te-IN" in out
    assert "friendly" in out


def test_empty_channels_use_defaults():
    out = build_agent_instructions(core_instructions="core", language="te-IN")
    assert "--- BEHAVIOUR ---" in out
    assert "--- BUSINESS ---" in out
