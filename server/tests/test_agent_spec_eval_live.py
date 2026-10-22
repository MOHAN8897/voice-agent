"""
Live Model Eval Suite for AgentSpec Pipeline (Requirement 7b).
Evaluates extraction accuracy using tolerant token-set comparison, reporting an overall pass rate.
Keeps Case #1 as the user's exact brief.
"""
import pytest
from server.brain.agent_spec_extractor import extract_agent_spec
from server.providers.registry import get_provider_registry


EVAL_CASES = [
    # Case #1: User's Exact Brief
    {
        "id": "eval_1_user_exact_brief",
        "brief": (
            "We sell flats and plots. Ask which project they are interested in, their budget "
            "and preferred configuration, then book a site visit. business name is mohan private limited "
            "and the person who calls the users is sindhuja and business location is in hyderabad. vanasthalipuram."
        ),
        "language_code": "te-IN",
        "expected_agent_tokens": {"sindhuja"},
        "expected_company_tokens": {"mohan", "private", "limited"},
        "forbidden_agent_tokens": {"priya", "alex"},
    },
    # Case #2: Insurance Agency
    {
        "id": "eval_2_insurance",
        "brief": "We sell health insurance policies. Company is Aditya Birla Health Insurance and caller is Kailash.",
        "language_code": "en-IN",
        "expected_agent_tokens": {"kailash"},
        "expected_company_tokens": {"aditya", "birla"},
        "forbidden_agent_tokens": {"priya", "alex"},
    },
    # Case #3: Real Estate Gated Community
    {
        "id": "eval_3_real_estate",
        "brief": "We are Chandana Infra developers. Sales caller is Mohan. We offer plots in Shadnagar.",
        "language_code": "te-IN",
        "expected_agent_tokens": {"mohan"},
        "expected_company_tokens": {"chandana", "infra"},
        "forbidden_agent_tokens": {"priya", "alex"},
    },
]


def _tokens(text: str | None) -> set[str]:
    import re
    return set(re.findall(r"\w+", (text or "").lower()))


@pytest.mark.asyncio
async def test_live_model_eval_suite_reports_pass_rate():
    """
    Runs evaluation across cases with tolerant token-set comparisons.
    Computes and reports the overall pass rate.
    """
    passed = 0
    total = len(EVAL_CASES)
    results = []

    for case in EVAL_CASES:
        spec = await extract_agent_spec(case["brief"], language_code=case["language_code"])
        agent_tokens = _tokens(spec.agent_name.value)
        company_tokens = _tokens(spec.company_name.value)

        # Tolerant checks: expected tokens must overlap, forbidden must not exist
        agent_match = bool(case["expected_agent_tokens"].intersection(agent_tokens))
        company_match = bool(case["expected_company_tokens"].intersection(company_tokens))
        no_forbidden = not bool(case["forbidden_agent_tokens"].intersection(agent_tokens))

        is_success = agent_match and company_match and no_forbidden
        if is_success:
            passed += 1

        results.append({
            "case_id": case["id"],
            "agent_name": spec.agent_name.value,
            "company_name": spec.company_name.value,
            "extraction_source": spec.extraction_source,
            "passed": is_success,
        })

    pass_rate = (passed / total) * 100.0
    print(f"\n[LIVE EVAL SUITE] Completed {total} cases. Pass Rate: {pass_rate:.1f}% ({passed}/{total})")
    for r in results:
        print(f"  - {r['case_id']}: agent='{r['agent_name']}' company='{r['company_name']}' src={r['extraction_source']} passed={r['passed']}")

    # Pass rate must be 100% on golden cases
    assert pass_rate == 100.0
    # Case #1 specifically:
    assert results[0]["passed"] is True
    assert "sindhuja" in results[0]["agent_name"].lower()
