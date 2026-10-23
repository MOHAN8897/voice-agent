"""
Stage 4 Tests: Confirmation Flow, Preview/Extract, Edit-and-Regenerate, and Creation Gates.
"""
import pytest

from server.agent.instruction_store import instruction_store
from server.app import app
from server.brain.agent_spec import AgentSpec, Evidenced
from server.tests.auth_helpers import authenticated_dev_client

client = None


@pytest.fixture(autouse=True)
def _authorized_http_workflow():
    global client
    client = authenticated_dev_client(app)

USER_BRIEF = (
    "We sell flats and plots. Ask which project they are interested in, their budget "
    "and preferred configuration, then book a site visit. business name is mohan private limited "
    "and the person who calls the users is sindhuja and business location is in hyderabad. vanasthalipuram."
)


def test_extract_spec_endpoint_previews_without_saving():
    session_id = "test-extract-preview-sid"
    instruction_store.clear(session_id)

    response = client.post(
        "/api/instructions/extract-spec",
        json={
            "agentBrief": USER_BRIEF,
            "language_code": "te-IN",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert "agentSpec" in data
    spec = data["agentSpec"]
    assert spec["agent_name"]["value"] == "Sindhuja"
    assert "Mohan Private Limited" in spec["company_name"]["value"]
    assert "specHash" in data

    # Verify preview did NOT create or persist an agent
    meta = instruction_store.get_with_meta(session_id)
    assert meta.get("usingDefaults") is True or not meta.get("agentScript")


def test_extract_spec_endpoint_fails_if_language_code_absent():
    response = client.post(
        "/api/instructions/extract-spec",
        json={
            "agentBrief": USER_BRIEF,
            "language_code": "",
        },
    )
    assert response.status_code == 400
    assert "language_code" in str(response.json())


def test_compile_from_spec_regenerates_script_without_reextraction():
    spec = AgentSpec(
        agent_name=Evidenced(value="Sindhuja", evidence="sindhuja", confidence=1.0),
        company_name=Evidenced(value="Mohan Private Limited", evidence="mohan private limited", confidence=1.0),
        location=Evidenced(value="Vanasthalipuram, Hyderabad", evidence="hyderabad. vanasthalipuram", confidence=1.0),
        call_objective=Evidenced(value="Book a site visit", evidence="book a site visit", confidence=1.0),
        offering=Evidenced(value="Flats and plots", evidence="flats and plots", confidence=1.0),
        qualification_questions=[
            "Which project are you interested in?",
        ],
        language_code="te-IN",
    )

    response = client.post(
        "/api/instructions/compile-from-spec",
        json={
            "spec": spec.model_dump(),
            "direction": "outbound",
            "recording_disclosure_enabled": True,
            "force": False,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    script = data["agentScript"]
    assert "Sindhuja" in script
    assert "Mohan Private Limited" in script
    assert "recorded" in script.lower()
    assert data["lintIssues"] == []


def test_compile_from_spec_blocks_when_needs_user_input():
    spec = AgentSpec(
        agent_name=Evidenced(value="Sindhuja", evidence="sindhuja", confidence=1.0),
        company_name=Evidenced(value=None, evidence=None, confidence=0.0),
        language_code="te-IN",
        needs_user_input=["company_name"],
    )

    # Blocked without force
    response = client.post(
        "/api/instructions/compile-from-spec",
        json={
            "spec": spec.model_dump(),
            "force": False,
        },
    )
    assert response.status_code == 400
    assert "needs_user_input" in response.text

    # Allowed with force
    force_response = client.post(
        "/api/instructions/compile-from-spec",
        json={
            "spec": spec.model_dump(),
            "force": True,
        },
    )
    assert force_response.status_code == 200


def test_save_instructions_blocks_create_when_needs_user_input_and_allows_force():
    session_id = "test-gate-user-input-sid"
    instruction_store.clear(session_id)

    spec_data = {
        "agent_name": {"value": "Sindhuja", "evidence": "sindhuja", "confidence": 1.0},
        "language_code": "te-IN",
        "needs_user_input": ["company_name"],
        "extraction_source": "gemini",
    }

    # Blocked without forceCreate
    res_blocked = client.post(
        "/api/instructions",
        json={
            "sessionId": session_id,
            "agentSpec": spec_data,
            "forceCreate": False,
        },
    )
    assert res_blocked.status_code == 400
    assert "needs_user_input" in res_blocked.text

    # Allowed with forceCreate
    res_allowed = client.post(
        "/api/instructions",
        json={
            "sessionId": session_id,
            "agentSpec": spec_data,
            "forceCreate": True,
        },
    )
    assert res_allowed.status_code == 200, res_allowed.text
    data = res_allowed.json()
    assert data["ok"] is True
    assert data["agentSpec"]["agent_name"]["value"] == "Sindhuja"
    instruction_store.clear(session_id)


def test_save_instructions_requires_confirmation_on_regex_fallback():
    session_id = "test-gate-regex-fallback-sid"
    instruction_store.clear(session_id)

    spec_data = {
        "agent_name": {"value": "Sindhuja", "evidence": "sindhuja", "confidence": 0.4},
        "company_name": {"value": "Mohan Private Limited", "evidence": "mohan private limited", "confidence": 0.4},
        "language_code": "te-IN",
        "extraction_source": "regex_fallback",
        "needs_user_input": [],
    }

    # Blocked without forceCreate
    res_blocked = client.post(
        "/api/instructions",
        json={
            "sessionId": session_id,
            "agentSpec": spec_data,
            "forceCreate": False,
        },
    )
    assert res_blocked.status_code == 400
    assert "confirmation_required" in res_blocked.text

    # Allowed with forceCreate
    res_allowed = client.post(
        "/api/instructions",
        json={
            "sessionId": session_id,
            "agentSpec": spec_data,
            "forceCreate": True,
        },
    )
    assert res_allowed.status_code == 200, res_allowed.text
    data = res_allowed.json()
    assert data["ok"] is True
    assert data["agentSpec"]["extraction_source"] == "regex_fallback"
    instruction_store.clear(session_id)
