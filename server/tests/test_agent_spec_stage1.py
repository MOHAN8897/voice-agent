import pytest
from pydantic import ValidationError
from server.brain.agent_spec import AgentSpec, Evidenced, verify_agent_spec


def test_agent_spec_requires_explicit_language_code():
    with pytest.raises(ValidationError):
        # language_code is required without default
        AgentSpec(language_code="")  # type: ignore[call-arg]

    spec = AgentSpec(language_code="te-IN")
    assert spec.language_code == "te-IN"


def test_verify_agent_spec_clips_legal_suffix_clause():
    brief = (
        "We sell flats and plots. business name is mohan private limited and the person who calls "
        "the users is sindhuja and business location is in hyderabad. vanasthalipuram."
    )
    raw_spec = AgentSpec(
        language_code="en-IN",
        company_name=Evidenced(
            value="mohan private limited and the person",
            evidence="business name is mohan private limited and the person",
            confidence=0.8,
        ),
        agent_name=Evidenced(
            value="sindhuja",
            evidence="person who calls the users is sindhuja",
            confidence=0.9,
        ),
        location=Evidenced(
            value="hyderabad, vanasthalipuram",
            evidence="business location is in hyderabad. vanasthalipuram",
            confidence=0.9,
        ),
        offering=Evidenced(
            value="flats and plots",
            evidence="We sell flats and plots",
            confidence=0.9,
        ),
        call_objective=Evidenced(
            value="book a site visit",
            evidence="then book a site visit",
            confidence=0.9,
        ),
    )

    verified = verify_agent_spec(raw_spec, brief)
    assert verified.company_name.value == "Mohan Private Limited"
    assert verified.agent_name.value == "Sindhuja"
    assert "and the person" not in (verified.company_name.value or "")
    assert verified.needs_user_input == []


def test_verify_agent_spec_preserves_company_names_with_and():
    brief = "Welcome to Mohan and Sons Real Estate. We offer villas in Bangalore."
    raw_spec = AgentSpec(
        language_code="en-IN",
        company_name=Evidenced(
            value="Mohan and Sons Real Estate",
            evidence="Mohan and Sons Real Estate",
            confidence=0.9,
        ),
        agent_name=Evidenced(
            value="Kavya",
            evidence="Kavya",
            confidence=0.8,
        ),
        offering=Evidenced(
            value="villas",
            evidence="We offer villas",
            confidence=0.9,
        ),
    )
    verified = verify_agent_spec(raw_spec, brief)
    assert verified.company_name.value == "Mohan and Sons Real Estate"


def test_verify_agent_spec_rejects_hallucinated_evidence():
    brief = "We sell sports equipment in Mumbai."
    raw_spec = AgentSpec(
        language_code="en-IN",
        company_name=Evidenced(
            value="Nike Global Inc",
            evidence="Nike Global Inc is our company",  # Not in brief
            confidence=0.9,
        ),
        offering=Evidenced(
            value="sports equipment",
            evidence="sports equipment",
            confidence=0.9,
        ),
    )
    verified = verify_agent_spec(raw_spec, brief)
    # Hallucinated company name rejected
    assert verified.company_name.value is None
    assert "company_name" in verified.needs_user_input


def test_verify_agent_spec_denylist_old_defaults():
    brief = "We provide logistics services in Delhi."
    raw_spec = AgentSpec(
        language_code="en-IN",
        company_name=Evidenced(
            value="Delhi Logistics Ltd",
            evidence="Delhi Logistics Ltd",
            confidence=0.9,
        ),
        agent_name=Evidenced(
            value="Priya",  # Default name fabricated by LLM, not in brief
            evidence="Priya",
            confidence=0.5,
        ),
        offering=Evidenced(
            value="logistics services",
            evidence="logistics services",
            confidence=0.9,
        ),
    )
    verified = verify_agent_spec(raw_spec, brief, tenant_default_agent_name="Support Bot")
    # Priya rejected because it was not in brief; falls back to tenant default persona
    assert verified.agent_name.value == "Support Bot"


def test_spec_hash_deterministic():
    spec1 = AgentSpec(
        language_code="te-IN",
        agent_name=Evidenced(value="Sindhuja"),
        company_name=Evidenced(value="Mohan Private Limited"),
    )
    spec2 = AgentSpec(
        language_code="te-IN",
        agent_name=Evidenced(value="Sindhuja"),
        company_name=Evidenced(value="Mohan Private Limited"),
    )
    assert spec1.spec_hash() == spec2.spec_hash()
