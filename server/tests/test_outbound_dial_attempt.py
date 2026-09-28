import pytest

from server.services.outbound_dial_attempt import (
    AttemptConflict,
    claim_attempt,
    execute_dial_attempt,
    get_attempt,
    save_attempt,
)


@pytest.mark.asyncio
async def test_execute_dial_attempt_replays_completed_response(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()

    async def dial():
        return {"ok": True, "callId": "c-1"}

    first = await execute_dial_attempt(
        request_id="req-abc",
        scope="test:tenant:user:telnyx",
        payload={"to": "+15551234567"},
        operation=dial,
    )
    assert first["ok"] is True

    async def should_not_run():
        raise AssertionError("carrier dial must not run twice for the same request id")

    second = await execute_dial_attempt(
        request_id="req-abc",
        scope="test:tenant:user:telnyx",
        payload={"to": "+15551234567"},
        operation=should_not_run,
    )
    assert second == first


@pytest.mark.asyncio
async def test_execute_dial_attempt_marks_uncertain_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()

    async def boom():
        raise TimeoutError("carrier timeout")

    with pytest.raises(TimeoutError):
        await execute_dial_attempt(
            request_id="req-uncertain",
            scope="test:scope",
            payload={"x": 1},
            operation=boom,
        )
    row = get_attempt("req-uncertain", scope="test:scope")
    assert row is not None
    assert row.get("status") == "uncertain"


def test_claim_attempt_rejects_fingerprint_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from server.config.env import get_settings

    get_settings.cache_clear()
    claim_attempt("rid", scope="s", fingerprint="a")
    with pytest.raises(AttemptConflict):
        claim_attempt("rid", scope="s", fingerprint="b")
