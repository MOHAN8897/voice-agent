"""OpenAI model parameter compatibility tests."""
from server.services.openai_model_params import (
    apply_generation_params,
    supports_temperature,
    voice_reasoning_effort,
)


def test_gpt5_omits_temperature():
    assert supports_temperature("gpt-5") is False
    assert supports_temperature("gpt-5.5") is False
    assert supports_temperature("gpt-5.6-luna") is False
    assert supports_temperature("o3-mini") is False
    assert supports_temperature("o4-mini") is False


def test_apply_generation_params_gpt5():
    kw: dict = {"model": "gpt-5", "input": []}
    apply_generation_params(kw, model="gpt-5", temperature=0.7, default_temperature=0.5, voice_optimized=True)
    assert "temperature" not in kw
    assert kw["reasoning"] == {"effort": "low"}


def test_apply_generation_params_luna():
    kw: dict = {"model": "gpt-5.6-luna", "input": []}
    apply_generation_params(kw, model="gpt-5.6-luna", temperature=0.3, default_temperature=0.5, voice_optimized=True)
    assert "temperature" not in kw
    assert kw["reasoning"] == {"effort": "none"}


def test_voice_reasoning_effort():
    assert voice_reasoning_effort("gpt-5.6-luna") == "none"
    assert voice_reasoning_effort("gpt-5.5") == "low"
