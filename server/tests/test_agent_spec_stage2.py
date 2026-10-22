import pytest
from unittest.mock import AsyncMock, patch

from server.brain.agent_spec_extractor import (
    extract_agent_spec,
    offline_regex_extract_agent_spec,
)
from server.brain.agent_spec import verify_agent_spec


@pytest.mark.asyncio
async def test_offline_regex_extract_user_exact_brief():
    brief = (
        "We sell flats and plots. Ask which project they are interested in, their budget and preferred "
        "configuration, then book a site visit. business name is mohan private limited and the person who "
        "calls the users is sindhuja and business location is in hyderabad. vanasthalipuram."
    )
    raw_spec = offline_regex_extract_agent_spec(brief, language_code="en-IN")
    verified = verify_agent_spec(raw_spec, brief)

    assert verified.agent_name.value == "Sindhuja"
    assert verified.company_name.value == "Mohan Private Limited"
    assert "and the person" not in (verified.company_name.value or "")
    assert verified.offering.value is not None and "flats and plots" in verified.offering.value.lower()
    assert verified.call_objective.value is not None and "site visit" in verified.call_objective.value.lower()
    assert verified.location.value is not None and "hyderabad" in verified.location.value.lower()
    assert verified.extraction_source == "regex_fallback"
    assert verified.agent_name.value != "Priya"


@pytest.mark.asyncio
async def test_provider_failover_gemini_to_openai():
    brief = "We sell solar panels. Company is SunPower Ltd. Callers are handled by Rahul."
    mock_gemini_error = AsyncMock(side_effect=RuntimeError("Gemini 401 Invalid Key"))

    mock_openai_success = AsyncMock(
        return_value={
            "agent_name": {"value": "Rahul", "evidence": "handled by Rahul", "confidence": 0.95},
            "company_name": {"value": "SunPower Ltd", "evidence": "SunPower Ltd", "confidence": 0.95},
            "location": {"value": None, "evidence": None, "confidence": 0.0},
            "offering": {"value": "solar panels", "evidence": "sell solar panels", "confidence": 0.9},
            "call_objective": {"value": "qualify leads", "evidence": None, "confidence": 0.5},
            "qualification_questions": ["power usage"],
            "constraints": [],
        }
    )

    with patch(
        "server.brain.agent_spec_extractor._attempt_provider_structured_extraction",
        side_effect=[mock_gemini_error.side_effect, mock_openai_success.return_value],
    ):
        spec = await extract_agent_spec(
            brief,
            language_code="en-IN",
            preferred_providers=["gemini", "openai"],
        )

        assert spec.agent_name.value == "Rahul"
        assert spec.company_name.value == "SunPower Ltd"
        assert spec.extraction_source == "llm_openai"


@pytest.mark.asyncio
async def test_all_providers_fail_falls_back_to_verified_regex():
    brief = "We sell dental implants. Business is Smile Care Clinics. The person who calls is Sneha."

    with patch(
        "server.brain.agent_spec_extractor._attempt_provider_structured_extraction",
        side_effect=RuntimeError("All LLMs offline"),
    ):
        spec = await extract_agent_spec(
            brief,
            language_code="en-IN",
            preferred_providers=["gemini", "openai"],
        )

        assert spec.agent_name.value == "Sneha"
        assert spec.company_name.value == "Smile Care Clinics"
        assert spec.extraction_source == "regex_fallback"
