"""Console-facing brain endpoints: read/edit the calling script and voice config.

These are the routes the four-step creation flow uses, so the contract matters:
the script the user reviewed is the script that gets stored and published.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.brain.business_brain_store import business_brain_store
from server.brain.compiled_brain_service import compiled_brain_service
from server.config.env import get_settings


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    return TestClient(app_mod.app)


def _create_agent(client) -> str:
    response = client.post("/api/agents", json={"name": f"Agent {uuid.uuid4().hex[:6]}"})
    assert response.status_code == 200, response.text
    return response.json()["agent"]["agent_id"]


def test_calling_script_round_trips(client):
    agent_id = _create_agent(client)
    script = "Greet the caller. Ask budget. Book a site visit. Say goodbye."

    saved = client.put(
        f"/api/agents/{agent_id}/business-brain/calling-script",
        json={"script": script},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ok"] is True

    read = client.get(f"/api/agents/{agent_id}/business-brain/calling-script")
    assert read.status_code == 200
    assert read.json()["callingScript"] == script


def test_calling_script_edit_preserves_other_sections(client):
    """Editing the script must not wipe voice config or variables."""
    agent_id = _create_agent(client)

    client.put(
        f"/api/agents/{agent_id}/business-brain/voice",
        json={"voiceId": "marin", "speed": 1.1, "language": "en-IN"},
    )
    client.put(
        f"/api/agents/{agent_id}/business-brain/calling-script",
        json={"script": "First script."},
    )
    client.put(
        f"/api/agents/{agent_id}/business-brain/calling-script",
        json={"script": "Second script, reworded by the user."},
    )

    brain = client.get(f"/api/agents/{agent_id}/business-brain").json()
    titles = {s.get("title") for s in brain["draft"]["sections"]}
    assert "Calling script" in titles
    assert "saas_voice_config" in titles
    script_section = next(s for s in brain["draft"]["sections"] if s["title"] == "Calling script")
    assert script_section["raw_text"] == "Second script, reworded by the user."


def test_voice_config_round_trips(client):
    agent_id = _create_agent(client)
    saved = client.put(
        f"/api/agents/{agent_id}/business-brain/voice",
        json={"voiceId": "cedar", "speed": 0.9, "language": "te-IN"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["voice"]["voiceId"] == "cedar"
    assert saved.json()["voice"]["speed"] == pytest.approx(0.9)
    assert saved.json()["voice"]["language"] == "te-IN"


def test_voice_config_defaults_are_filled_in(client):
    agent_id = _create_agent(client)
    voice = client.put(
        f"/api/agents/{agent_id}/business-brain/voice",
        json={"voiceId": "marin", "speed": 1.0, "language": "en-IN"},
    ).json()["voice"]
    # The runtime needs these; the console should not have to supply them.
    assert voice["turnDetection"] == "semantic_vad"
    assert voice["noiseReduction"] == "far_field"


def test_voice_config_is_stored_disabled(client):
    """Voice settings are read by the runtime, not injected into the LLM prompt."""
    agent_id = _create_agent(client)
    client.put(
        f"/api/agents/{agent_id}/business-brain/voice",
        json={"voiceId": "marin", "speed": 1.0, "language": "en-IN"},
    )
    brain = client.get(f"/api/agents/{agent_id}/business-brain").json()
    voice_section = next(
        s for s in brain["draft"]["sections"] if s["title"] == "saas_voice_config"
    )
    assert voice_section["enabled"] is False


def test_calling_script_rejects_an_empty_script(client):
    agent_id = _create_agent(client)
    response = client.put(
        f"/api/agents/{agent_id}/business-brain/calling-script",
        json={"script": "   "},
    )
    # The app normalises validation failures to 400.
    assert response.status_code == 400
    assert "script" in response.text


def test_voice_config_rejects_an_out_of_range_speed(client):
    agent_id = _create_agent(client)
    response = client.put(
        f"/api/agents/{agent_id}/business-brain/voice",
        json={"voiceId": "marin", "speed": 9.0, "language": "en-IN"},
    )
    # The app normalises validation failures to 400.
    assert response.status_code == 400
    assert "speed" in response.text


def test_unknown_agent_is_404(client):
    response = client.get(f"/api/agents/{uuid.uuid4()}/business-brain/calling-script")
    assert response.status_code == 404


def test_saved_script_reaches_the_compiled_brain(client):
    """What the user reviewed must be what the live voice pipeline is given.

    The outbound path refuses an agent with no compiled brain, so this also proves
    the agent becomes callable once its script is saved.
    """
    agent_id = _create_agent(client)
    script = "Answer the call. Ask for the order number. Confirm the delivery date."

    client.put(
        f"/api/agents/{agent_id}/business-brain/calling-script",
        json={"script": script},
    )

    preview = client.get(f"/api/agents/{agent_id}/brain/compiled-preview?redacted=false")
    assert preview.status_code == 200, preview.text
    assert preview.json()["compiled_version"]
    # The business script is part of the compiled prompt the agent actually runs.
    assert "order number" in preview.json()["preview"]


def test_writing_a_script_for_an_unknown_agent_is_404(client):
    """Orphan brain sections must not be creatable for an agent that does not exist."""
    response = client.put(
        f"/api/agents/{uuid.uuid4()}/business-brain/calling-script",
        json={"script": "This should not be stored."},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "not_found"
