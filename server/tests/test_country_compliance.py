"""Regression coverage for India's tenant-facing advisory checklist."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.saas.country_compliance import (
    compliance_catalog,
    compliance_for_country,
    merge_agent_compliance,
)


@pytest.mark.parametrize("country", [None, "", "  ", "in", "IN"])
def test_default_market_is_india_and_no_obligation_is_preacknowledged(country):
    result = merge_agent_compliance(None, country)
    assert result["country"] == "IN"
    assert result["countryName"] == "India"
    assert "TRAI" in result["regulation"]
    assert "TCPA" not in result["regulation"]
    assert result["acknowledged"]
    assert not any(result["acknowledged"].values())
    assert all(" " in item["label"] for item in result["obligations"])
    assert len(result["sources"]) == 4
    assert any("13 May 2027" in note for note in result["notes"])
    assert any("18 September 2026" in note for note in result["notes"])


def test_checklist_is_india_only_regardless_of_the_assigned_number():
    for country in ("US", "GB", "CA", "AU", "SG", "ZZ"):
        result = compliance_for_country(country)
        assert result["country"] == "IN"
        assert "TRAI" in result["regulation"]
        assert "TCPA" not in result["regulation"]
        assert "PECR" not in result["regulation"]
    catalog = compliance_catalog()
    assert [entry["country"] for entry in catalog] == ["IN"]
    assert catalog[0]["dial"] == "+91"


def test_saved_acknowledgements_are_preserved_but_new_and_unknown_keys_are_not_confirmed():
    result = merge_agent_compliance({"acknowledged": {
        "identify_sender": True,
        "recording_disclosure": False,
        "unrecognised_control": True,
    }}, "IN")
    assert result["acknowledged"]["identify_sender"] is True
    assert result["acknowledged"]["recording_disclosure"] is False
    assert result["acknowledged"]["do_not_call_registry"] is False
    assert "unrecognised_control" not in result["acknowledged"]


def test_acknowledgements_do_not_carry_to_a_different_market():
    result = merge_agent_compliance({"country": "US", "acknowledged": {"identify_sender": True}}, "IN")
    assert not any(result["acknowledged"].values())


@pytest.mark.asyncio
async def test_compliance_save_persists_only_known_acknowledgements_for_this_market(monkeypatch):
    from server.routes import app_telephony
    from server.services.saas import activity_log

    tenant_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    row = SimpleNamespace(agent_id=agent_id, tenant_id=tenant_id, voice_settings={"existing_setting": "keep"})
    commit = AsyncMock()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, key):
            assert key == agent_id
            return row

        async def commit(self):
            await commit()

    monkeypatch.setattr(app_telephony, "get_session_factory", lambda: Session)
    monkeypatch.setattr(app_telephony, "require_subscriber_permission", lambda *args: None)
    monkeypatch.setattr(activity_log, "record_event", AsyncMock())
    principal = SimpleNamespace(tenant_id=tenant_id, email="operator@example.invalid", user_id=uuid.uuid4())
    result = await app_telephony.put_agent_compliance(
        str(agent_id),
        app_telephony.ComplianceBody(acknowledged={"identify_sender": True, "unknown_flag": True}),
        principal,
    )
    assert result["acknowledged"]["identify_sender"] is True
    assert "unknown_flag" not in row.voice_settings["compliance"]["acknowledged"]
    assert row.voice_settings["compliance"]["country"] == "IN"
    assert row.voice_settings["existing_setting"] == "keep"
    commit.assert_awaited_once()
