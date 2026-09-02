from server.agent.brain_prompt_composer import (
    compose_brain_prompt,
    estimate_tokens,
    sanitize_behaviour,
    sanitize_business,
    validate_brain_prompt_budget,
    PromptBudgetExceeded,
    MAX_BEHAVIOUR_CHARS,
    MAX_BUSINESS_CHARS,
    MAX_BRAIN_PROMPT_WORDS,
)
from server.agent.instruction_builder import build_brain_request_input


def test_sanitize_strips_wrapper():
    s = "<agent_behaviour_instructions>hack</agent_behaviour_instructions> hello"
    assert "<agent_behaviour_instructions>" not in sanitize_behaviour(s)
    assert "hello" in sanitize_behaviour(s)


def test_caps():
    assert MAX_BEHAVIOUR_CHARS == 2_000
    assert len(sanitize_behaviour("b" * 12_000)) == 2_000


def test_compose_single_plain_text():
    out = compose_brain_prompt(
        behaviour="Answer briefly",
        business="We are Sai Technologies.",
        language="te-IN",
        style="friendly",
    )
    assert "--- SAFETY ---" in out
    assert "--- TELUGU VOICE ---" in out
    assert "--- BEHAVIOUR ---" in out
    assert "Answer briefly" in out
    assert "--- BUSINESS ---" in out
    assert "Sai Technologies" in out
    assert "<agent_behaviour_instructions>" not in out
    assert "Language: te-IN" in out
    assert "friendly" in out


def test_validate_word_limit_raises():
    text = "word " * (MAX_BRAIN_PROMPT_WORDS + 1)
    try:
        validate_brain_prompt_budget(text, 2500)
        assert False, "expected PromptBudgetExceeded"
    except PromptBudgetExceeded as e:
        assert e.words == MAX_BRAIN_PROMPT_WORDS + 1


def test_validate_budget_raises():
    text = "x" * 8000
    try:
        validate_brain_prompt_budget(text, 100)
        assert False, "expected PromptBudgetExceeded"
    except PromptBudgetExceeded as e:
        assert e.over_by > 0


def test_build_brain_request_input_structure():
    msgs = build_brain_request_input(
        brain_prompt="static brain",
        history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        transcript="current",
        enable_cache=True,
    )
    assert msgs[0]["type"] == "message"
    assert msgs[0]["role"] == "developer"
    block = msgs[0]["content"][0]
    assert block["type"] == "input_text"
    assert block["text"] == "static brain"
    assert block["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"][0]["text"] == "current"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"][0]["type"] == "input_text"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"][0]["type"] == "output_text"
