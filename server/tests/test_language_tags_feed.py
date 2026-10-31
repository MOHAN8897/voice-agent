"""Home feed items say which language a caller asked for, on every status and on the calls involved."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.services.saas import activity_feed_service as feed


def _request(status: str):
    return SimpleNamespace(id=uuid.uuid4(), requested_language="hi-IN", original_language="te-IN",
                           contact_name="Ravi", phone_e164="+919000000002", original_call_id=uuid.uuid4(),
                           status=status, request_text="Hindi mein baat karo", agent_id=str(uuid.uuid4()),
                           updated_at=datetime.now(timezone.utc))


@pytest.mark.parametrize("status", ["pending", "calling", "done"])
def test_language_items_carry_the_requested_language_on_every_status(status):
    item = feed._language_item(_request(status), {})
    assert item["meta"]["language"] == "hi-IN" and item["meta"]["languageLabel"] == "Hindi"


def _call_row(call_id: str):
    return SimpleNamespace(status_tags=["followup:language_switch"], agent_id=uuid.uuid4(), end_reason="", disposition="",
                           duration_sec=40, call_id=call_id, campaign_id=None, direction="inbound", status="completed",
                           started_at=datetime.now(timezone.utc), ended_at=None, answered_at=None)


def test_calls_carry_the_asked_for_and_callback_languages_with_the_substitution_note(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    tenant = str(uuid.uuid4())
    asked, callback = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        for call_id, meta in (
            (asked, {"language_callback": {"status": "requested", "caller_language": "hi-IN"}}),
            (callback, {"direction": "outbound", "contact": {
                "call_language": "hi-IN", "language_switch_id": "x",
                "language_substitutions": [{"line": "farewell", "fromLanguage": "te-IN", "toLanguage": "hi-IN"}]}}),
        ):
            call_ledger.meta_path(call_id).parent.mkdir(parents=True, exist_ok=True)
            call_ledger.write_meta(call_id, {"call_id": call_id, "tenant_id": tenant, **meta})
        info = feed._ledger_details(asked, tenant)
        item = feed._call_item(_call_row(asked), {})
        item["_enrich"](item, info)
        assert item["meta"]["language"] == "hi-IN" and item["meta"]["languageLabel"] == "Hindi"

        info = feed._ledger_details(callback, tenant)
        item = feed._call_item(_call_row(callback), {})
        item["_enrich"](item, info)
        assert item["meta"]["callLanguageLabel"] == "Hindi"
        assert item["meta"]["languageNote"] == ("Used the standard Hindi goodbye because your custom one is in "
                                               "Telugu. Add a Hindi version in the script.")
    finally:
        get_settings.cache_clear()
