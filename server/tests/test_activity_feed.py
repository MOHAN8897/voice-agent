"""Console activity feed: every item type from seeded rows, tenant isolation, filters, cursor, live rail.

SQLite stands in for Postgres (ARRAY/JSONB columns become JSON for the test only).
No carrier, no LLM, no wallet charge: the feed is read-only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.db.models.concurrency_models import TenantChannelEvent, TenantChannelSubscription
from server.db.models.entities import Agent, Call, CallAttempt, CallCallback, Tenant
from server.db.models.followup_models import FollowUpJob
from server.db.models.integration_models import TenantIntegration, ToolExecution
from server.db.models.language_switch_models import LanguageSwitchRequest
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, PhoneNumber
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead
from server.services.saas import activity_feed_service as feed

TABLES = [Tenant, Agent, Call, CallAttempt, CallCallback, FollowUpJob, LanguageSwitchRequest, Lead, Campaign,
          CampaignContact, CampaignRun, ToolExecution, TenantIntegration, PhoneNumber, BillingWallet,
          BillingWalletTransaction, TenantChannelEvent, TenantChannelSubscription]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
async def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    changed = [(c, c.type) for m in TABLES for c in m.__table__.columns if isinstance(c.type, (ARRAY, JSONB))]
    for c, _ in changed:
        c.type = JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'feed.db'}")
    try:
        async with engine.begin() as conn:
            for m in TABLES:
                await conn.run_sync(lambda sync, t=m.__table__: t.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(feed, "get_session_factory", lambda: factory)
        yield factory
    finally:
        await engine.dispose()
        for c, original in changed:
            c.type = original
        get_settings.cache_clear()


async def _tenant(factory, name="Meera"):
    tid, aid = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add_all([Tenant(tenant_id=tid, name=f"Tenant {name}"), Agent(agent_id=aid, tenant_id=tid, name=name)])
        await s.commit()
    return tid, aid


def _call(tid, aid, *, minutes_ago=10, **kw):
    started = _now() - timedelta(minutes=minutes_ago)
    base = dict(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="t", storage_path="t",
                channel="pstn", direction="inbound", started_at=started, ended_at=started + timedelta(minutes=2),
                duration_sec=120, status="answered", status_tags=[], is_test=False)
    base.update(kw)
    return Call(**base)


def _ledger(call_id, tid, phone="+919876543123", name=None, **extra):
    call_ledger.meta_path(str(call_id)).parent.mkdir(parents=True, exist_ok=True)
    meta = {"call_id": str(call_id), "tenant_id": str(tid), "direction": "inbound", "caller_id": phone, **extra}
    if name:
        meta["contact"] = {"name": name}
    call_ledger.write_meta(str(call_id), meta)


async def _seed_everything(factory, tid, aid):
    """One row per feed item type."""
    now = _now()
    calls = {
        "completed": _call(tid, aid, minutes_ago=60, disposition="qualified"),
        "booked": _call(tid, aid, minutes_ago=55, disposition="site_visit_planned", status_tags=["followup:site_visit"]),
        "technical": _call(tid, aid, minutes_ago=50, end_reason="technical_failure"),
        "dnd": _call(tid, aid, minutes_ago=45, end_reason="opt_out", status_tags=["signal:do_not_call"]),
        "live": _call(tid, aid, minutes_ago=2, ended_at=None, duration_sec=None, status="in_progress"),
        "test": _call(tid, aid, minutes_ago=40, is_test=True),
    }
    camp_id = uuid.uuid4()
    async with factory() as s:
        s.add_all(calls.values())
        s.add(CallAttempt(attempt_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, provider_call_control_id=str(uuid.uuid4()),
                          direction="inbound", from_number="+919811122233", status="missed",
                          started_at=now - timedelta(minutes=35)))
        s.add(CallCallback(callback_id=uuid.uuid4(), tenant_id=tid, original_call_id=calls["completed"].call_id,
                           agent_id=str(aid), to_e164="+919876543123", dial_request_id=f"requested:{uuid.uuid4()}",
                           mode="requested", status="requested", created_at=now - timedelta(minutes=30)))
        for status, ago in (("needs_review", 29), ("scheduled", 28), ("completed", 27)):
            s.add(FollowUpJob(tenant_id=tid, agent_id=aid, origin_key=str(uuid.uuid4()), source_id=str(uuid.uuid4()),
                              kind="callback", phone="+919800000001", status=status,
                              reason="call_connected" if status == "completed" else "approval_required",
                              payload={"requestedWhen": "after 6pm"}, due_at=now + timedelta(hours=3),
                              expires_at=now + timedelta(days=2), created_at=now - timedelta(minutes=ago),
                              updated_at=now - timedelta(minutes=ago)))
        s.add(LanguageSwitchRequest(id=uuid.uuid4(), tenant_id=tid, agent_id=str(aid), phone_e164="+919800000002",
                                    contact_name="Ravi", requested_language="hi-IN", original_language="te-IN",
                                    status="pending", created_at=now - timedelta(minutes=26),
                                    updated_at=now - timedelta(minutes=26)))
        s.add(Lead(lead_id=uuid.uuid4(), tenant_id=tid, agent_id=str(aid), name="Anita", phone="+919800000003",
                   stage="new", created_at=now - timedelta(minutes=25), updated_at=now - timedelta(minutes=25)))
        s.add(Lead(lead_id=uuid.uuid4(), tenant_id=tid, agent_id=str(aid), name="Kiran", stage="qualified",
                   created_at=now - timedelta(days=1), updated_at=now - timedelta(minutes=24)))
        s.add(Campaign(campaign_id=camp_id, tenant_id=tid, agent_id=aid, name="Diwali offers", status="completed",
                       created_at=now - timedelta(minutes=23)))
        s.add(CampaignRun(run_id=uuid.uuid4(), campaign_id=camp_id, status="completed",
                          started_at=now - timedelta(minutes=22), ended_at=now - timedelta(minutes=21)))
        s.add_all([CampaignContact(campaign_id=camp_id, phone_e164="+919800000010", status="completed"),
                   CampaignContact(campaign_id=camp_id, phone_e164="+919800000011", status="pending")])
        s.add(ToolExecution(tenant_id=tid, agent_id=aid, call_id=str(calls["booked"].call_id),
                            action="google_calendar.create_event", action_type="write", idempotency_key="k1",
                            status="succeeded", parameters={}, started_at=now - timedelta(minutes=20)))
        s.add(TenantIntegration(tenant_id=tid, app_name="hubspot", connection_id="c1", status="ERROR",
                                metadata_={}, created_at=now, updated_at=now - timedelta(minutes=19)))
        s.add(PhoneNumber(tenant_id=tid, e164="+918000000001", status="active", agent_id=aid,
                          created_at=now - timedelta(minutes=18)))
        s.add(PhoneNumber(tenant_id=tid, e164="+918000000002", status="suspended_unpaid",
                          created_at=now - timedelta(days=40)))
        s.add(BillingWallet(tenant_id=tid, balance_cents=0, balance_inr_paise=12_000, updated_at=now))
        s.add(BillingWalletTransaction(tenant_id=tid, amount_cents=0, amount_inr_paise=200_000,
                                       kind="razorpay_topup_inr", created_at=now - timedelta(minutes=17)))
        s.add(BillingWalletTransaction(tenant_id=tid, amount_cents=0, amount_inr_paise=-50_000,
                                       kind="did_rental", created_at=now - timedelta(minutes=16)))
        s.add(BillingWalletTransaction(tenant_id=tid, amount_cents=-1, amount_inr_paise=-100,
                                       kind="usage_pstn", created_at=now - timedelta(minutes=15)))
        s.add(TenantChannelSubscription(tenant_id=tid, paid_channels=2, status="grace",
                                        grace_until=now + timedelta(days=2), updated_at=now))
        s.add(TenantChannelEvent(tenant_id=tid, kind="renewal_failed", channels_before=2, channels_after=2,
                                 created_at=now - timedelta(minutes=14)))
        await s.commit()
    for key, call in calls.items():
        _ledger(call.call_id, tid, name="Ravi Kumar" if key == "booked" else None)
    return calls


def _types(page):
    return {i["type"] for i in page["items"]} | {i["type"] for i in page["pinned"]}


async def test_every_item_type_appears_from_seeded_rows(db):
    tid, aid = await _tenant(db)
    calls = await _seed_everything(db, tid, aid)
    page = await feed.build_feed(tid, limit=60)
    types = _types(page)
    expected = {
        "call.live", "call.completed", "call.booked", "call.technical", "call.dnd", "call.missed",
        "callback.requested", "followup.review", "callback.due", "followup.done", "language.callback",
        "lead.created", "lead.qualified", "campaign.started", "campaign.completed", "campaign.created",
        "integration.action", "integration.reconnect", "number.provisioned", "number.suspended",
        "billing.topup", "billing.rent", "billing.low", "channel.grace", "channel.renewal_failed",
    }
    assert expected <= types, expected - types
    everything = page["items"] + page["pinned"]
    # Live calls sort first; browser practice sessions never appear.
    assert page["items"][0]["type"] == "call.live"
    assert str(calls["test"].call_id) not in {i["refs"].get("callId") for i in everything}
    # Usage debits are not feed events.
    assert not any("usage" in (i["text"] or "").lower() for i in everything)
    booked = next(i for i in everything if i["type"] == "call.booked")
    assert booked["actor"] == "Meera" and "site visit with Ravi Kumar" in booked["text"]
    # Contact numbers are shown in full but formatted (never as raw digit strings);
    # the dial action carries the call id, not the number.
    language = next(i for i in everything if i["type"] == "language.callback")
    assert language["needsAction"] and "Hindi" in language["text"]
    assert language["actions"][0]["kind"] == "call_in_language"
    serialized = repr(everything)
    for raw in ("+919876543123", "+919811122233", "+919800000002", "+919800000001"):
        assert raw not in serialized
    missed = next(i for i in everything if i["type"] == "call.missed")
    assert missed["contact"]["phone"] == "+91 98111 22233"
    assert "+91 98111 22233" in missed["text"]
    assert missed["actions"][0] == {"kind": "call_back", "label": "Call back", "callId": missed["refs"]["callId"]}
    # Internal vocabulary never reaches the sentence.
    for item in everything:
        assert "_" not in (item["text"] or "").replace("Phone line", ""), item["text"]
    review = next(i for i in everything if i["type"] == "followup.review")
    assert {a["kind"] for a in review["actions"]} >= {"approve_followup", "reject_followup"}
    assert page["needsActionCount"] >= 6
    wallet = next(i for i in everything if i["type"] == "billing.low")
    assert "₹120" in wallet["text"] and wallet["tone"] == "warning"
    topup = next(i for i in everything if i["type"] == "billing.topup")
    assert topup["text"].startswith("₹2,000")


async def test_tenant_isolation(db):
    tid, aid = await _tenant(db, "Meera")
    other, other_agent = await _tenant(db, "Hima")
    await _seed_everything(db, tid, aid)
    page = await feed.build_feed(other, limit=60)
    ids = {i["id"] for i in page["items"] + page["pinned"]}
    # The other tenant only sees its own empty-wallet alert.
    assert ids == {"alert:wallet"}
    live = await feed.live_snapshot(other)
    assert live["calls"] == [] and live["today"]["calls"] == 0


async def test_filters_and_agent_filter(db):
    tid, aid = await _tenant(db)
    await _seed_everything(db, tid, aid)
    calls = await feed.build_feed(tid, filter_="calls", limit=60)
    # Bookings are calls too, so they show under Calls as well as Leads & bookings.
    assert {i["category"] for i in calls["items"]} == {"calls", "leads"}
    assert all(i["type"].startswith(("call.", "callback.", "followup.", "language.")) for i in calls["items"])
    leads = await feed.build_feed(tid, filter_="leads", limit=60)
    assert {i["type"] for i in leads["items"]} <= {"lead.created", "lead.qualified", "call.booked"}
    assert "call.booked" in {i["type"] for i in leads["items"]}
    campaigns = await feed.build_feed(tid, filter_="campaigns", limit=60)
    assert {i["category"] for i in campaigns["items"]} == {"campaigns"}
    completed = next(i for i in campaigns["items"] if i["type"] == "campaign.completed")
    assert completed["meta"]["progress"] == {"total": 2, "done": 1}
    system = await feed.build_feed(tid, filter_="system", limit=60)
    assert {i["category"] for i in system["items"]} == {"system"}
    needs = await feed.build_feed(tid, filter_="needs_action", limit=60)
    assert needs["items"] and all(i["needsAction"] for i in needs["items"])
    assert needs["pinned"] == []
    # Another agent's filter hides this agent's work and the workspace billing items.
    stranger = await feed.build_feed(tid, agent_id=str(uuid.uuid4()), limit=60)
    assert stranger["items"] == [] and stranger["pinned"] == []
    mine = await feed.build_feed(tid, agent_id=str(aid), limit=60)
    assert mine["items"] and all(i["agentId"] in (str(aid), None) for i in mine["items"])
    assert not any(i["category"] == "system" and i["type"].startswith("billing") for i in mine["items"])
    assert (await feed.build_feed(tid, agent_id="not-a-uuid"))["items"] == []


async def test_cursor_pagination_has_no_gaps_or_duplicates(db):
    tid, aid = await _tenant(db)
    async with db() as s:
        s.add_all([_call(tid, aid, minutes_ago=i + 5) for i in range(23)])
        await s.commit()
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = await feed.build_feed(tid, filter_="calls", limit=5, cursor=cursor)
        seen.extend(i["id"] for i in page["items"])
        pages += 1
        if cursor is not None:
            assert page["pinned"] == []
        cursor = page["nextCursor"]
        if not cursor:
            break
        assert pages < 10
    assert len(seen) == 23 == len(set(seen))
    stamps = [feed.decode_cursor(feed.encode_cursor(datetime(2026, 10, 30, 1, 2, 3, 456789, tzinfo=timezone.utc), "k"))]
    assert stamps[0] == (datetime(2026, 10, 30, 1, 2, 3, 456789, tzinfo=timezone.utc), "k")


async def test_live_endpoint_lists_calls_in_progress_and_today(db):
    tid, aid = await _tenant(db)
    live_call = _call(tid, aid, minutes_ago=3, ended_at=None, duration_sec=None, status="in_progress")
    stale = _call(tid, aid, minutes_ago=600, ended_at=None, duration_sec=None, status="in_progress")
    done = _call(tid, aid, minutes_ago=30, duration_sec=200, disposition="site_visit_planned")
    async with db() as s:
        s.add_all([live_call, stale, done])
        await s.commit()
    _ledger(live_call.call_id, tid, name="Ravi")
    snap = await feed.live_snapshot(tid, since=_now() - timedelta(hours=5))
    assert [c["callId"] for c in snap["calls"]] == [str(live_call.call_id)]
    assert snap["calls"][0]["agentName"] == "Meera"
    assert snap["calls"][0]["contact"] == {"name": "Ravi", "phone": "+91 98765 43123"}
    assert snap["today"]["calls"] == 1 and snap["today"]["talkSeconds"] == 200 and snap["today"]["bookings"] == 1


async def test_booking_intent_alone_is_not_reported_as_booked(db):
    tid, aid = await _tenant(db)
    call = _call(tid, aid, minutes_ago=5, disposition="converted", status_tags=["intent:booking"])
    async with db() as s:
        s.add(call)
        await s.commit()
    _ledger(call.call_id, tid, name="Mohan")
    page = await feed.build_feed(tid, limit=20)
    item = next(i for i in page["items"] if i["refs"].get("callId") == str(call.call_id))
    assert item["text"] == "talked with Mohan about booking an appointment"


async def test_item_detail_rebuilds_every_item_with_its_source_call(db):
    tid, aid = await _tenant(db)
    other, _ = await _tenant(db, "Hima")
    calls = await _seed_everything(db, tid, aid)
    page = await feed.build_feed(tid, limit=60)
    everything = page["items"] + page["pinned"]
    for listed in everything:
        detail = await feed.item_detail(tid, listed["id"])
        assert detail is not None, listed["id"]
        assert detail["item"]["id"] == listed["id"] and detail["item"]["type"] == listed["type"]
        # Another workspace can never open this tenant's item.
        if not listed["id"].startswith("alert:"):
            assert await feed.item_detail(other, listed["id"]) is None, listed["id"]

    booked = next(i for i in everything if i["type"] == "call.booked")
    detail = await feed.item_detail(tid, booked["id"])
    call = detail["call"]
    assert call["call_id"] == str(calls["booked"].call_id)
    assert call["agent_name"] == "Meera" and call["outcome_label"] == "Site visit planned"
    assert "tenant_id" not in call
    actions = detail["related"]["integrationActions"]
    assert actions and actions[0]["type"] == "integration.action"

    completed = next(i for i in everything if i["type"] == "call.completed")
    related = (await feed.item_detail(tid, completed["id"]))["related"]
    assert [r["type"] for r in related["callbacks"]] == ["callback.requested"]

    callback = next(i for i in everything if i["type"] == "callback.requested")
    detail = await feed.item_detail(tid, callback["id"])
    assert detail["call"]["call_id"] == str(calls["completed"].call_id)
    assert detail["facts"]["status"] == "requested"
    assert all(r["id"] != callback["id"] for r in detail["related"]["callbacks"])

    lead = next(i for i in everything if i["type"] == "lead.created")
    detail = await feed.item_detail(tid, lead["id"])
    assert detail["lead"]["name"] == "Anita" and detail["lead"]["stage"] == "new"

    finished = next(i for i in everything if i["type"] == "campaign.completed")
    detail = await feed.item_detail(tid, finished["id"])
    assert detail["campaign"]["progress"] == {"total": 2, "done": 1}
    assert detail["campaign"]["statusCounts"] == {"completed": 1, "pending": 1}

    topup = next(i for i in everything if i["type"] == "billing.topup")
    assert (await feed.item_detail(tid, topup["id"]))["facts"]["amount"] == "₹2,000"
    channel = next(i for i in everything if i["type"] == "channel.renewal_failed")
    assert (await feed.item_detail(tid, channel["id"]))["facts"]["channelsAfter"] == 2

    for bogus in ("", "call:", "call:not-a-uuid", f"call:{uuid.uuid4()}", "nonsense:1", f"lead:{uuid.uuid4()}:new"):
        assert await feed.item_detail(tid, bogus) is None, bogus
    # Browser practice sessions are not activity.
    assert await feed.item_detail(tid, f"call:{calls['test'].call_id}") is None


async def test_new_tenant_feed_is_empty_but_explains_wallet(db):
    tid, _ = await _tenant(db)
    page = await feed.build_feed(tid)
    assert page["items"] == []
    assert [p["type"] for p in page["pinned"]] == ["billing.low"]


def test_indian_numbers_format_the_same_with_or_without_country_code():
    for raw in ("+918897123470", "918897123470", "8897123470"):
        assert feed.format_phone(raw) == "+91 88971 23470", raw
    # A number stored as the contact's name is shown formatted, not as a raw digit string.
    assert feed._contact("918897123470", None) == {"name": None, "phone": "+91 88971 23470"}
    assert feed._contact("Mohan", "+918897123470")["name"] == "Mohan"


def test_phone_format_and_money_helpers():
    assert feed.format_phone("+919876543123") == "+91 98765 43123"
    assert feed.format_phone("+12025550123") == "+1 202 555 0123"
    assert feed.format_phone("04023456789") == "+91 40 2345 6789"
    assert feed.format_phone("+442071838750") == "+442 071 838 750"
    assert feed.format_phone("") is None
    # Old name still works for existing imports.
    assert feed.mask_phone is feed.format_phone
    assert feed.money_inr(12_345_600) == "₹1,23,456"
    assert feed.money_inr(12_050) == "₹120.50"


async def test_routes_are_registered_and_tenant_scoped(db, monkeypatch):
    from fastapi.testclient import TestClient

    from server.app import app
    from server.auth.subscriber_dependencies import require_subscriber_jwt
    from server.services.saas.tenant_guard import SubscriberPrincipal

    tid, aid = await _tenant(db)
    await _seed_everything(db, tid, aid)
    principal = SubscriberPrincipal(uuid.uuid4(), tid, "customer_admin", "feed@example.invalid")
    app.dependency_overrides[require_subscriber_jwt] = lambda: principal
    monkeypatch.setattr("server.routes.activity_feed.subscriber_workspace_tenant_id", lambda p: p.tenant_id)
    try:
        client = TestClient(app)
        res = client.get("/api/activity/feed?limit=10&filter=calls")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["items"] and body["filter"] == "calls"
        assert client.get("/api/activity/feed?filter=bogus").status_code in (400, 422)
        live = client.get("/api/activity/live")
        assert live.status_code == 200 and len(live.json()["calls"]) == 1
        item_id = body["items"][0]["id"]
        detail = client.get("/api/activity/item", params={"id": item_id})
        assert detail.status_code == 200, detail.text
        assert detail.json()["item"]["id"] == item_id
        assert client.get("/api/activity/item", params={"id": f"call:{uuid.uuid4()}"}).status_code == 404
    finally:
        app.dependency_overrides.pop(require_subscriber_jwt, None)
