"""Regressions for independently reproduced defects in the Telugu audit."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call.memory_guard import grounded_turn_operations
from server.call.memory_manager import MemoryManager, empty_snapshot
from server.services.tool_router import VoxlyToolRouter
from server.services.saas.lead_scoring import score_outcome


def test_rejected_product_cannot_become_selected_product():
    caller = "నాకు మగ్స్ వద్దు, కార్డులు కావాలి"
    operations = grounded_turn_operations([
        {"op": "set_fact", "key": "product", "value": "మగ్స్", "evidence": caller}
    ], caller)
    assert operations == [], "Rejected mugs were accepted as the selected product"


def test_same_email_create_deduplicates_when_optional_phone_is_added():
    router = VoxlyToolRouter()
    first = router._generate_idempotency_key("tenant", "call", "HUBSPOT_CREATE_CONTACT", {
        "email": "audit@example.invalid", "firstname": "Test"
    })
    second = router._generate_idempotency_key("tenant", "call", "HUBSPOT_CREATE_CONTACT", {
        "email": "audit@example.invalid", "firstname": "Test", "phone": "+12025550123"
    })
    assert first == second, "Adding an optional phone permits a second CREATE for the same email"


def test_new_lead_without_buying_evidence_gets_no_interest_points():
    result = score_outcome({"disposition": "new_lead", "disposition_confidence": .95, "facts": {}})
    interest = next(c for c in result["components"] if c["signal"] == "interest")
    assert interest["points"] == 0, "Generic new_lead is being treated as buying evidence"


def test_delayed_old_memory_write_cannot_replace_new_snapshot(monkeypatch):
    manager = MemoryManager()
    manager._state["call"] = empty_snapshot()
    manager._events["call"] = []
    old_write_entered, release_old = Event(), Event()
    persisted = {}

    def write(_call, snapshot):
        if snapshot["facts"]["city"] == "Old":
            old_write_entered.set()
            assert release_old.wait(5)
        persisted["snapshot"] = snapshot

    monkeypatch.setattr(manager, "_append_event", lambda *args: None)
    monkeypatch.setattr(manager, "_write_snapshot", write)
    monkeypatch.setattr("server.call.redis_memory_cache.set_snapshot", lambda *args: None)
    with ThreadPoolExecutor(max_workers=2) as workers:
        old = workers.submit(manager.apply_proposals, "call", [
            {"op": "set_fact", "key": "city", "value": "Old"}], turn_seq=1)
        assert old_write_entered.wait(5)
        try:
            new = workers.submit(manager.apply_proposals, "call", [
                {"op": "set_fact", "key": "city", "value": "New"}], turn_seq=2)
            # Persistence may serialize, but hot reads must remain available.
            import time
            deadline = time.monotonic() + 2
            while manager.peek_snapshot("call")["facts"]["city"] != "New" and time.monotonic() < deadline:
                time.sleep(.005)
            assert manager.peek_snapshot("call")["facts"]["city"] == "New"
        finally:
            release_old.set()
        old.result(timeout=5)
        new.result(timeout=5)
    assert manager.peek_snapshot("call")["facts"]["city"] == "New"
    assert persisted["snapshot"]["facts"]["city"] == "New", "Old disk/cache state overwrote the newer memory"


def test_business_answers_reject_forged_source_and_compute_supported_total():
    from server.call.business_answer_plan import validate_answers
    rows = ['Matte cards: 100 cost 350 rupees.', 'Fridge inspection costs 250.']
    result = validate_answers([
        dict(domain='business_terms', question='200 matte total', row_id=0, topic_quote='Matte cards', value_quote='350',
             unit_price_quote='350', unit_quantity_quote='100', requested_quantity_quote='200'),
        dict(domain='business_terms', question='AC inspection', row_id=1, topic_quote='AC inspection', value_quote='250'),
        dict(domain='business_terms', question='missing', row_id=True, topic_quote='Fridge', value_quote='250'),
        dict(domain='caller_memory', question='Did you note 200?', row_id=None),
    ], rows, 'I need 200 matte cards')
    assert result[0]['calculated_total'] == '700'
    assert [r['status'] for r in result[1:]] == ['not_stated', 'not_stated']
    # A numeric substring isn't a source price, and bundle pricing doesn't
    # establish whether fractional bundles are sold.
    for price, quantity in [('50', '200'), ('350', '150')]:
        value = validate_answers([dict(domain='business_terms', question='total', row_id=0, topic_quote='Matte cards', value_quote='350',
            unit_price_quote=price, unit_quantity_quote='100', requested_quantity_quote=quantity)], rows, quantity)[0]
        assert 'calculated_total' not in value


def test_unreviewed_model_cannot_close_or_modify_contact_scope():
    from server.call.semantic_call_control import gate
    ctx = SimpleNamespace(status='active', agent_hangup_armed=False,
        callback_request_text='keep this callback', callback_close_phase='pending', callback_when='tomorrow')
    raw = dict(decision='close', reason='firm_refusal', evidence='stop',
               contact_intent='do_not_call', contact_evidence='stop')
    result = gate(raw, ctx=ctx, transcript='stop', language='en-IN')
    assert not result['should_end']
    assert result['reject_code'] == 'close_not_verified'
    assert ctx.callback_request_text == 'keep this callback'
    assert not ctx.agent_hangup_armed


@pytest.mark.asyncio
async def test_future_scope_check_does_not_trust_quoted_current_call_refusal():
    from server.call.close_classifier import _verify_future_opt_out
    class Adapter:
        async def stream_live_turn(self, **kwargs):
            yield dict(done=True, text='{"future_calls_forbidden": false, "evidence": "end this call"}')
    assert await _verify_future_opt_out(Adapter(), SimpleNamespace(model='pinned', config={}), 'end this call', None) == ''


def test_long_clear_question_does_not_imply_speaking_too_fast():
    from server.call.live_turn_orchestrator import live_turn_orchestrator
    assert live_turn_orchestrator._maybe_slow_down_hint('Please explain. ' * 100,
        language_code='en-IN', call_id=None, ctx=SimpleNamespace()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('initial_type,uncertain,requested,expected_writes', [
    ('read', False, 'write', 1), ('write', False, 'write', 0),
    ('read', True, 'write', 0), ('read', False, 'read', 0),
])
async def test_calendar_continuation_is_bounded_and_never_repeats_uncertain_write(
    monkeypatch, initial_type, uncertain, requested, expected_writes,
):
    from server.call.live_turn_orchestrator import LiveTurnOrchestrator
    from server.services.tool_router import tool_router
    orch = LiveTurnOrchestrator()
    executions = []
    async def execute(**kwargs):
        executions.append(kwargs['tool_calls'])
        kwargs['turn_state']['action_outcome_unconfirmed'] = uncertain
        return kwargs['messages'] or []
    async def select(**kwargs):
        # Even a model asking for duplicate writes must execute at most one.
        yield dict(done=True, tool_calls=[{'function': {'name': 'CREATE_EVENT'}}] * 2)
    async def speak(**kwargs):
        assert kwargs['stream_kwargs']['tool_choice'] == 'none'
        yield dict(done=True, text='confirmed')
    monkeypatch.setattr(orch, '_execute_composed_tools', execute)
    monkeypatch.setattr(orch, '_stream_composed_turn', select)
    monkeypatch.setattr(orch, '_stream_composed_speech', speak)
    monkeypatch.setattr(tool_router, '_get_action_metadata', lambda name: {'type': 'write' if name == 'CREATE_EVENT' else 'read'})
    chunks = [c async for c in orch._composed_speech_after_tools(
        ctx=SimpleNamespace(turn_control={'action_request': requested}),
        adapter=SimpleNamespace(selects_tools_without_schema=True, stream_live_turn=None),
        llm_sel=SimpleNamespace(provider='sarvam', model='pinned'), stream_kwargs={}, messages=[],
        tool_schemas=[{'name': 'FIND_SLOTS'}, {'name': 'CREATE_EVENT'}],
        tool_calls=[{'function': {'name': 'FIND_SLOTS' if initial_type == 'read' else 'CREATE_EVENT'}}],
        call_id=None, record_request_usage=lambda _: None, allow_retry=False,
    )]
    assert len(executions) == 1 + expected_writes
    if expected_writes:
        assert len(executions[-1]) == 1
    assert chunks[-1]['text'] == 'confirmed'


@pytest.mark.asyncio
async def test_fact_review_never_speaks_internal_verdict(monkeypatch):
    from server.call.spoken_fact_review import review_spoken_turn
    from server.providers import get_provider_registry
    class Adapter:
        async def stream_live_turn(self, **kwargs):
            yield dict(done=True, text='The inspection fee is unknown.\n__OK__')
    monkeypatch.setattr(get_provider_registry(), 'get_llm', lambda _: Adapter())
    ctx = SimpleNamespace(call_id='fact-review', session_id='fact-review', compiled_brain_text='Approved business facts.',
        resolved_stack=SimpleNamespace(llm=SimpleNamespace(provider='sarvam', model='pinned', config={})))
    answer = await review_spoken_turn(ctx, caller='What is the fee?', draft='Free.', language='en-IN')
    assert answer == 'The inspection fee is unknown.'
