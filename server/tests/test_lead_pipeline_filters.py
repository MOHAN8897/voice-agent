"""Real SQL queries through the HTTP boundary, on disposable tenant fixtures."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.db.models.entities import Base
from server.db.models.saas_models import Lead
from server.routes import app_leads
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.tests.test_integration_security_hardening import AID, FOREIGN, OTHER, TID
from server.tests.test_integration_security_hardening import db as shared_db

db = shared_db
OWN = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000201")
FOREIGN_LEAD = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000202")


@pytest.fixture
async def client(db, monkeypatch):
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Lead.__table__]))
    now = datetime.now(timezone.utc)
    async with db() as session:
        session.add_all([Lead(lead_id=OWN if i == 0 else uuid.uuid4(), tenant_id=TID, agent_id=str(AID),
            name=f"Enquiry {i:02d}", phone=None if i == 0 else f"+1202555{i:04d}",
            email=f"enquiry{i}@example.invalid", notes="Needs a demo" if i == 0 else "Price 20% agreed",
            stage="qualified" if i % 2 == 0 else "new", created_at=now,
            updated_at=now - timedelta(days=i)) for i in range(31)])
        session.add_all([
            Lead(lead_id=FOREIGN_LEAD, tenant_id=OTHER, agent_id=str(FOREIGN), name="Foreign secret", stage="qualified"),
            Lead(tenant_id=TID, agent_id=None, name="Workspace lead", stage="new", phone="  "),
        ])
        await session.commit()
    monkeypatch.setattr(app_leads, "get_session_factory", lambda: db)
    app = FastAPI()
    app.include_router(app_leads.router)

    async def principal(authorization: str | None = Header(None)):
        if authorization != "Bearer fixture-only":
            raise HTTPException(401)
        return SubscriberPrincipal(user_id=uuid.UUID(int=9), tenant_id=TID, role="customer_admin", email="owner@example.invalid")

    app.dependency_overrides[require_subscriber_jwt] = principal
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": "Bearer fixture-only"}) as value:
        yield value


async def test_pagination_and_counts_cover_all_matches_without_foreign_rows(client):
    result = (await client.get("/api/leads", params={"agentId": str(AID), "limit": 25})).json()
    assert result["total"] == 31
    assert len(result["leads"]) == 25
    assert result["stageCounts"] == {"qualified": 16, "new": 15}
    assert all(row["agentId"] == str(AID) for row in result["leads"])
    next_page = (await client.get("/api/leads", params={"agentId": str(AID), "offset": 25, "limit": 25})).json()
    assert len(next_page["leads"]) == 6
    assert {row["leadId"] for row in next_page["leads"]}.isdisjoint(row["leadId"] for row in result["leads"])
    assert (await client.get("/api/leads", params={"agentId": str(FOREIGN)})).json()["total"] == 0


async def test_stage_search_phone_date_and_unassigned_filters_are_server_side(client):
    filtered = (await client.get("/api/leads", params={"stage": "qualified", "search": "enquiry0@example.invalid", "hasPhone": "false"})).json()
    assert filtered["total"] == 1 and filtered["leads"][0]["leadId"] == str(OWN)
    recent = (await client.get("/api/leads", params={"updatedSince": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()})).json()
    assert recent["total"] == 2
    unassigned = (await client.get("/api/leads", params={"agentId": "unassigned", "hasPhone": "false"})).json()
    assert unassigned["total"] == 1 and unassigned["leads"][0]["name"] == "Workspace lead"
    # Percent is literal user text, not a SQL wildcard that matches every row.
    assert (await client.get("/api/leads", params={"search": "%"})).json()["total"] == 30
    assert (await client.get("/api/leads", params={"stage": "invented"})).status_code == 422


async def test_lead_edits_persist_together_and_forbid_cross_tenant_assignment(client, db):
    response = await client.patch(f"/api/leads/{OWN}", json={"stage": "meeting_booked", "notes": "Demo agreed for Friday"})
    assert response.status_code == 200
    assert response.json()["lead"]["stage"] == "meeting_booked"
    async with db() as session:
        row = await session.scalar(select(Lead).where(Lead.lead_id == OWN))
        assert row.notes == "Demo agreed for Friday"
    assert (await client.patch(f"/api/leads/{OWN}", json={"agentId": str(FOREIGN)})).status_code == 404
    assert (await client.patch(f"/api/leads/{FOREIGN_LEAD}", json={"notes": "overwrite"})).status_code == 404
    assert (await client.patch(f"/api/leads/{FOREIGN_LEAD}/stage", json={"stage": "new"})).status_code == 404
    assert (await client.patch("/api/leads/invalid-id", json={"notes": "x"})).status_code == 404


async def test_stale_lead_edit_is_rejected_and_explicit_null_unassigns(client):
    first = (await client.get("/api/leads", params={"agentId": str(AID)})).json()["leads"][0]
    path = f"/api/leads/{first['leadId']}"
    saved = await client.patch(path, json={"notes": "Saved newer note", "expectedUpdatedAt": first["updatedAt"]})
    assert saved.status_code == 200
    conflict = await client.patch(path, json={"notes": "Stale overwrite", "expectedUpdatedAt": first["updatedAt"]})
    assert conflict.status_code == 409
    cleared = await client.patch(path, json={"agentId": None, "notes": None, "expectedUpdatedAt": saved.json()["lead"]["updatedAt"]})
    assert cleared.status_code == 200
    assert cleared.json()["lead"]["agentId"] is None and cleared.json()["lead"]["notes"] is None


async def test_creation_validates_owner_and_blank_name_and_route_requires_auth(client):
    assert (await client.post("/api/leads", json={"name": "New enquiry", "agentId": str(FOREIGN)})).status_code == 404
    assert (await client.post("/api/leads", json={"name": "  "})).status_code == 422
    response = await client.post("/api/leads", json={"name": " New enquiry ", "agentId": str(AID), "notes": "Please call"})
    assert response.status_code == 200 and response.json()["lead"]["agentId"] == str(AID)
    assert response.json()["lead"]["name"] == "New enquiry"
    assert (await client.get("/api/leads", headers={"Authorization": "invalid"})).status_code == 401


async def test_converted_requires_confirmation_persists_and_filters(client):
    assert (await client.patch(f"/api/leads/{OWN}", json={"stage": "converted"})).status_code == 409
    response = await client.patch(f"/api/leads/{OWN}", json={"stage": "converted", "confirmConverted": True})
    assert response.status_code == 200 and response.json()["lead"]["stage"] == "converted"
    result = (await client.get("/api/leads", params={"stage": "converted"})).json()
    assert result["total"] == 1 and result["stageCounts"] == {"converted": 1}


def test_ai_followups_do_not_change_confirmed_conversion():
    from server.services.saas.lead_sync import should_advance, stage_for_disposition
    assert stage_for_disposition("converted") == "qualified"
    assert not should_advance("qualified", "converted")
    assert not should_advance("meeting_booked", "converted")
