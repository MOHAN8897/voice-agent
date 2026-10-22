"""The dev-tester phone fallback must not leak phone or database details to logs."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
import uuid

import pytest

from server.services.saas import dev_tester_workspace


@pytest.mark.asyncio
async def test_phone_setup_failure_log_redacts_number_tenant_and_exception(caplog, monkeypatch) -> None:
    phone = "+12025550123"
    tenant_id = uuid.UUID("d881c159-dae3-4919-b05a-652c6a7c8e1f")

    class FailingSession:
        async def execute(self, _query):
            raise RuntimeError(f"database failure while inserting {phone}: private detail")

    @asynccontextmanager
    async def session_context():
        yield FailingSession()

    monkeypatch.setattr(dev_tester_workspace, "is_dev_tester_email", lambda _email: True)
    monkeypatch.setattr(
        dev_tester_workspace,
        "get_settings",
        lambda: SimpleNamespace(vobiz_phone_number=phone, telnyx_phone_number=None),
    )
    monkeypatch.setattr(
        dev_tester_workspace,
        "get_session_factory",
        lambda: lambda: session_context(),
    )
    monkeypatch.setattr(
        "server.services.telephony.active_telephony_provider",
        lambda: "vobiz",
    )

    with caplog.at_level("WARNING", logger="server.services.saas.dev_tester_workspace"):
        await dev_tester_workspace.ensure_dev_tester_phone_line(tenant_id, "tester@example.invalid")

    assert phone not in caplog.text
    assert str(tenant_id) not in caplog.text
    assert "private detail" not in caplog.text
    assert "error=RuntimeError" in caplog.text
