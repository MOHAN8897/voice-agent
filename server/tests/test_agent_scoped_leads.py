"""Agent-scoped leads: pool release, attribution, staging, and voice preview.

The regressions these cover were all invisible to a type checker: a deleted
agent kept its number, leads had no owner at all, and the "preview voice" button
spoke through a different engine than production.
"""
from __future__ import annotations

import io
import uuid
import wave
from types import SimpleNamespace

import pytest

from server.brain.agent_service import AgentService
from server.services.saas import lead_sync, voice_preview


# --------------------------------------------------------------------------
# Agent deletion must return its numbers to the pool
# --------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeSession:
    """Records the statements issued, without a database.

    Models the transaction semantics that caused the original bug: `rollback()`
    discards everything since the last `commit()`. A fake that treats rollback as
    a no-op would let the number-release-undo defect pass.
    """

    def __init__(self, rowcount: int = 2) -> None:
        self.rowcount = rowcount
        self.statements: list[tuple] = []
        self.committed_releases = 0
        self._uncommitted_release = 0
        self.commits = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        self._uncommitted_release += self.rowcount
        return _FakeResult(self.rowcount)

    async def commit(self) -> None:
        self.commits += 1
        self.committed_releases += self._uncommitted_release
        self._uncommitted_release = 0

    async def rollback(self) -> None:
        # Anything not yet committed is lost — exactly like a real session.
        self._uncommitted_release = 0


@pytest.mark.asyncio
async def test_deleting_an_agent_releases_its_numbers():
    session = _FakeSession(rowcount=3)
    released = await AgentService._release_agent_numbers(session, str(uuid.uuid4()))
    assert released == 3


@pytest.mark.asyncio
async def test_number_release_targets_only_that_agents_numbers():
    session = _FakeSession()
    agent_id = uuid.uuid4()
    await AgentService._release_agent_numbers(session, str(agent_id))

    params = session.statements[0].compile().params or {}
    values = list(params.values())
    # Scoped to this agent...
    assert agent_id in values or str(agent_id) in [str(v) for v in values]
    # ...and the column is being nulled, which is what frees it for reassignment.
    assert None in values, f"expected agent_id to be set to NULL, got {params}"


@pytest.mark.asyncio
async def test_release_reports_zero_when_the_agent_held_no_numbers():
    assert await AgentService._release_agent_numbers(_FakeSession(rowcount=0), str(uuid.uuid4())) == 0


@pytest.mark.asyncio
async def test_the_release_survives_the_rollback_of_a_failed_delete():
    """The regression that produced "(assigned elsewhere)" after deleting an agent.

    Deleting an agent whose call history blocks the hard delete falls back to
    archiving it, and that fallback rolls the session back. The number release
    must already be committed by then, or the rollback hands the number straight
    back to an agent the user can no longer see.
    """
    session = _FakeSession(rowcount=1)
    await AgentService._release_agent_numbers(session, str(uuid.uuid4()))

    # Simulate the archive fallback that follows a failed delete.
    await session.rollback()

    assert session.committed_releases == 1, "rollback undid the number release"


# --------------------------------------------------------------------------
# Disposition -> CRM stage
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "disposition,expected",
    [
        ("new_lead", "new"),
        ("interested", "contacted"),
        ("callback_required", "contacted"),
        ("qualified", "qualified"),
        ("converted", "qualified"),
        ("site_visit_planned", "meeting_booked"),
        ("not_interested", "unqualified"),
        ("wrong_number", "unqualified"),
        ("no_outcome", "new"),
    ],
)
def test_every_disposition_maps_to_a_real_stage(disposition, expected):
    stage = lead_sync.stage_for_disposition(disposition)
    assert stage == expected
    assert stage in lead_sync.STAGE_ORDER


def test_an_unknown_disposition_is_treated_as_a_new_lead():
    # Never crashes the pipeline, never invents a stage the board cannot render.
    assert lead_sync.stage_for_disposition("something_new") == "new"
    assert lead_sync.stage_for_disposition(None) == "new"


def test_a_stage_only_ever_moves_forward():
    assert lead_sync.should_advance("qualified", "contacted") is True
    assert lead_sync.should_advance("meeting_booked", "qualified") is True
    # A callback on a qualified lead must not devalue it.
    assert lead_sync.should_advance("contacted", "qualified") is False
    assert lead_sync.should_advance("qualified", "qualified") is False


def test_an_unrecognised_existing_stage_is_treated_as_the_bottom():
    assert lead_sync.should_advance("contacted", "garbage") is True


# --------------------------------------------------------------------------
# Rejections must not manufacture leads
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["not_interested", "wrong_number", "no_outcome"])
async def test_a_rejected_call_creates_no_lead(disposition, monkeypatch):
    def _fail_if_called():
        raise AssertionError("rejected call must not reach the database")

    monkeypatch.setattr(lead_sync, "_session_factory", _fail_if_called)
    result = await lead_sync.sync_outcome_to_lead(
        outcome={"disposition": disposition},
        tenant_id=str(uuid.uuid4()),
        agent_id=str(uuid.uuid4()),
    )
    assert result is None


@pytest.mark.asyncio
async def test_an_unusable_tenant_id_is_rejected_without_raising():
    result = await lead_sync.sync_outcome_to_lead(
        outcome={"disposition": "qualified"},
        tenant_id="not-a-uuid",
        agent_id=str(uuid.uuid4()),
    )
    assert result is None


# --------------------------------------------------------------------------
# Facts -> notes
# --------------------------------------------------------------------------

def test_notes_carry_the_summary_the_next_action_and_the_verdict():
    notes = lead_sync._notes_from_outcome(
        {
            "summary_en": "Wants a demo next Tuesday.",
            "next_action": "Book the demo",
            "objections": ["Too expensive"],
            "disposition": "site_visit_planned",
            "disposition_confidence": 0.8,
        }
    )
    assert "Wants a demo next Tuesday." in notes
    assert "Next step: Book the demo" in notes
    assert "Objections: Too expensive" in notes
    assert "site visit planned (80% confidence)" in notes


def test_notes_omit_empty_sections():
    notes = lead_sync._notes_from_outcome({"summary_en": "", "disposition": "qualified"})
    assert "Next step:" not in notes
    assert "Objections:" not in notes
    assert "qualified" in notes


def test_notes_are_bounded_so_one_long_call_cannot_exhaust_a_row():
    notes = lead_sync._notes_from_outcome({"summary_en": "x" * 5000})
    assert len(notes) <= 1200


# --------------------------------------------------------------------------
# Phone matching
# --------------------------------------------------------------------------

def test_phone_numbers_are_compared_by_digits_only():
    # +91 98765 43210 and 919876543210 are one lead, not two.
    assert lead_sync._phone_key("+91 98765 43210") == lead_sync._phone_key("919876543210") == "919876543210"


def test_the_caller_number_is_used_for_inbound_calls():
    phone = lead_sync._extract_phone({}, {"direction": "inbound", "caller_id": "+15551234567"})
    assert phone == "+15551234567"


def test_the_callee_number_is_used_for_outbound_calls():
    phone = lead_sync._extract_phone({}, {"direction": "outbound", "callee_e164": "+15559876543"})
    assert phone == "+15559876543"


def test_an_extracted_fact_beats_the_call_parties():
    facts = {"callback_phone": "+15550001111"}
    phone = lead_sync._extract_phone(facts, {"direction": "inbound", "caller_id": "+15551234567"})
    assert phone == "+15550001111"


# --------------------------------------------------------------------------
# Voice preview really is the live voice
# --------------------------------------------------------------------------

def test_pcm_is_wrapped_in_a_playable_wav():
    pcm = b"\x00\x01" * 24000  # 1s of 16-bit mono at 24kHz
    wav = voice_preview.pcm16_to_wav(pcm, 24000)
    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.readframes(wf.getnframes()) == pcm


def test_an_openai_catalog_voice_previews_as_its_gemini_counterpart():
    """The preview must speak the voice the call will use, not the OpenAI one."""
    voice, label = voice_preview.resolve_preview_voice("marin")
    assert voice == "Puck"
    assert label == "Marin"


def test_an_unknown_voice_falls_back_rather_than_failing():
    voice, _ = voice_preview.resolve_preview_voice("does-not-exist")
    assert voice


def test_preview_text_is_whitespace_collapsed_and_capped():
    # The cap bounds a billable live session, so it has to be enforced here.
    assert len(voice_preview.normalize_preview_text("a " * 5000)) == voice_preview.MAX_PREVIEW_CHARS
    assert voice_preview.normalize_preview_text("  hello\n\n  world  ") == "hello world"


def test_an_empty_preview_line_is_refused():
    with pytest.raises(ValueError):
        voice_preview.normalize_preview_text("   \n  ")