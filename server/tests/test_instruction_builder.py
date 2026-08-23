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
    # business sanitizer also strips behaviour tags
    z = sanitize_business("<business_context_instructions>x</business_context_instructions> ok")
    assert "<business_context_instructions>" not in z and "ok" in z


def test_caps_are_10k():
    assert MAX_BEHAVIOUR_INSTRUCTIONS == 10_000
    assert MAX_BUSINESS_INSTRUCTIONS == 10_000
    long_b = "b" * 12_000
    assert len(sanitize_behaviour(long_b)) == 10_000
    long_z = "z" * 12_000
    assert len(sanitize_business(long_z)) == 10_000


def test_build_wraps_both_channels():
    out = build_agent_instructions(
        core_instructions="core",
        behaviour_instructions="Answer briefly",
        business_instructions="We are Sai Technologies; refund window is 7 days.",
        language="te-IN",
        response_style="friendly",
    )
    assert "core" in out
    assert "<agent_behaviour_instructions>" in out and "Answer briefly" in out
    assert "<business_context_instructions>" in out and "Sai Technologies" in out
    assert "Language: te-IN" in out
    assert "friendly" in out


def test_empty_channels_no_wrapper():
    out = build_agent_instructions(core_instructions="core", language="te-IN")
    assert "<agent_behaviour_instructions>" not in out
    assert "<business_context_instructions>" not in out
