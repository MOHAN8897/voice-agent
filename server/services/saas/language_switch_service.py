"""Language-switch callback items: record in-call, list, call back in the requested language.

The live call records the item before the agent says a call back will be arranged
(``record_language_switch``). The tenant then calls the contact back with the same
agent in the requested language — one at a time (``call_language_switch``, through
the normal callback/outbound path) or as a campaign whose contacts each carry their
``call_language``. ``subscriber_outbound`` applies that language to the brain, STT,
TTS voice and pre-generated opening. A connected callback with a caller turn marks
the item done (``complete_language_switch_after_call``) and remembers the contact's
language.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.call.call_ledger import call_ledger
from server.db.connection import get_session_factory
from server.services.saas.call_callback_service import normalize_e164

logger = logging.getLogger(__name__)

STATUSES = ("pending", "calling", "done", "dismissed")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _models():
    from server.db.models.language_switch_models import ContactLanguagePreference, LanguageSwitchRequest

    return LanguageSwitchRequest, ContactLanguagePreference


def canonical_language(code: Any) -> str | None:
    from server.call.language_switch import code_for_language_name

    return code_for_language_name(str(code or ""))


def language_override_agent(agent: dict[str, Any], language: str) -> dict[str, Any]:
    """Same agent, this call speaks ``language``: it leads languages[] for stack resolution."""
    languages = [str(c) for c in (agent.get("languages") or [agent.get("language") or "te-IN"]) if c]
    return {**agent, "language": language, "languages": [language, *[c for c in languages if c != language]]}


# -- In-call recording --------------------------------------------------------------

def _contact_name(call_id: str, meta: dict[str, Any]) -> str | None:
    try:
        from server.call.memory_manager import memory_manager

        facts = (memory_manager.peek_snapshot(call_id) or {}).get("facts") or {}
    except Exception:
        facts = {}
    contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
    for value in (facts.get("caller_name"), contact.get("full_name"), contact.get("name"),
                  " ".join(str(contact.get(k) or "") for k in ("first_name", "last_name")).strip()):
        if isinstance(value, dict):
            value = value.get("value")
        if value and str(value).strip():
            return str(value).strip()[:255]
    return None


async def _upsert_item(session, *, tenant_id: uuid.UUID, agent_id: str, call_id: uuid.UUID | None, phone: str,
                       name: str | None, requested: str, original: str, request_text: str):
    Item, _ = _models()
    query = select(Item).where(Item.tenant_id == tenant_id, Item.original_call_id == call_id)
    row = (await session.execute(query)).scalar_one_or_none() if call_id else None
    if row is None:
        row = Item(id=uuid.uuid4(), tenant_id=tenant_id, agent_id=agent_id, original_call_id=call_id,
                   phone_e164=phone, contact_name=name, requested_language=requested, original_language=original,
                   request_text=request_text[:800] or None, status="pending", created_at=_now(), updated_at=_now())
        session.add(row)
    else:
        row.requested_language, row.updated_at = requested, _now()
        if row.status in ("dismissed",):
            row.status = "pending"
    return row


async def _remember_language(session, tenant_id: uuid.UUID, phone: str, language: str, source: str) -> None:
    _, Pref = _models()
    row = (await session.execute(select(Pref).where(Pref.tenant_id == tenant_id, Pref.phone_e164 == phone))).scalar_one_or_none()
    if row is None:
        session.add(Pref(id=uuid.uuid4(), tenant_id=tenant_id, phone_e164=phone, language=language, source=source, updated_at=_now()))
    else:
        row.language, row.source, row.updated_at = language, source, _now()


async def record_language_switch(ctx: Any, *, requested_language: str, original_language: str,
                                 request_text: str = "") -> dict[str, Any] | None:
    """Commit the item before the agent promises the callback. Never dials."""
    from server.call.language_switch import language_name

    try:
        tenant_id, call_id = uuid.UUID(str(ctx.tenant_id)), uuid.UUID(str(ctx.call_id))
    except (ValueError, TypeError, AttributeError):
        return None
    meta = await asyncio.to_thread(call_ledger.read_meta, str(call_id))
    phone = normalize_e164(meta.get("callee_e164") if meta.get("direction") == "outbound" else meta.get("caller_id"))
    if not phone:
        return None
    saved_id: str | None = None
    factory = get_session_factory()
    if factory is not None:
        async with factory() as session:
            row = await _upsert_item(session, tenant_id=tenant_id, agent_id=str(ctx.agent_id), call_id=call_id,
                                     phone=phone, name=_contact_name(str(call_id), meta), requested=requested_language,
                                     original=original_language, request_text=request_text)
            await _remember_language(session, tenant_id, phone, requested_language, "caller_request")
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                Item, _ = _models()
                row = (await session.execute(select(Item).where(Item.tenant_id == tenant_id,
                    Item.original_call_id == call_id))).scalar_one_or_none()
                if row is None:
                    return None
            saved_id = str(row.id)
    else:
        return None
    meta = await asyncio.to_thread(call_ledger.read_meta, str(call_id))
    meta["language_callback"] = {
        "status": "requested", "kind": "language_switch", "id": saved_id,
        "caller_language": requested_language, "configured_language": original_language,
        "summary": f"Caller asked to continue in {language_name(requested_language)}; "
                   f"call back in {language_name(requested_language)} with the same agent.",
    }
    await asyncio.to_thread(call_ledger.write_meta, str(call_id), meta)
    return {"id": saved_id, "language": requested_language}


async def ensure_language_switch_from_meta(call_id: str, meta: dict[str, Any]) -> str | None:
    """Post-call: make sure a requested language handoff (any voice stack) has its item."""
    handoff = meta.get("language_callback")
    if not isinstance(handoff, dict) or handoff.get("status") != "requested" or handoff.get("id"):
        return handoff.get("id") if isinstance(handoff, dict) else None
    if meta.get("contact_preference") == "do_not_call":
        return None
    requested = canonical_language(handoff.get("caller_language"))
    factory = get_session_factory()
    if not requested or factory is None:
        return None
    try:
        tenant_id, cid = uuid.UUID(str(meta.get("tenant_id"))), uuid.UUID(str(call_id))
    except (ValueError, TypeError):
        return None
    phone = normalize_e164(meta.get("callee_e164") if meta.get("direction") == "outbound" else meta.get("caller_id"))
    if not phone:
        return None
    async with factory() as session:
        row = await _upsert_item(session, tenant_id=tenant_id, agent_id=str(meta.get("agent_id") or ""), call_id=cid,
                                 phone=phone, name=_contact_name(call_id, meta), requested=requested,
                                 original=str(handoff.get("configured_language") or meta.get("language") or ""),
                                 request_text=str(handoff.get("summary") or ""))
        await _remember_language(session, tenant_id, phone, requested, "caller_request")
        await session.commit()
        return str(row.id)


# -- Completion after the callback ---------------------------------------------------

def _caller_spoke(call_id: str) -> bool:
    try:
        return any(r.get("role") == "user" and str(r.get("text") or "").strip() and not r.get("partial")
                   for r in call_ledger.read_lines(call_id))
    except Exception:
        return False


async def complete_language_switch_after_call(call_id: str, meta: dict[str, Any]) -> bool:
    """A connected callback in the requested language, with a caller turn, closes the item."""
    contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
    item_id = str(contact.get("language_switch_id") or "").strip()
    if not item_id:
        return False
    handoff = meta.get("language_callback")
    if isinstance(handoff, dict) and handoff.get("status") == "requested":
        return False  # the caller asked for yet another language; a new item tracks it
    if not await asyncio.to_thread(_caller_spoke, call_id):
        return False
    factory = get_session_factory()
    if factory is None:
        return False
    Item, _ = _models()
    try:
        tenant_id, iid = uuid.UUID(str(meta.get("tenant_id"))), uuid.UUID(item_id)
    except (ValueError, TypeError):
        return False
    async with factory() as session:
        row = (await session.execute(select(Item).where(Item.id == iid, Item.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status in ("done", "dismissed"):
            return False
        spoken = str(contact.get("call_language") or meta.get("language") or "")
        if spoken and canonical_language(spoken) != row.requested_language:
            return False
        row.status, row.completed_at, row.updated_at, row.error = "done", _now(), _now(), None
        try:
            row.callback_call_id = uuid.UUID(str(call_id))
        except (ValueError, TypeError):
            pass
        await _remember_language(session, tenant_id, row.phone_e164, row.requested_language, "callback_completed")
        await session.commit()
    return True


# -- Tenant surface ------------------------------------------------------------------

def _public(row) -> dict[str, Any]:
    from server.call.language_switch import language_name

    return {
        "id": str(row.id), "kind": row.kind, "callId": str(row.original_call_id) if row.original_call_id else None,
        "agentId": row.agent_id, "phone": row.phone_e164, "contactName": row.contact_name,
        "requestedLanguage": row.requested_language, "requestedLanguageLabel": language_name(row.requested_language),
        "originalLanguage": row.original_language, "originalLanguageLabel": language_name(row.original_language),
        "requestText": row.request_text or "", "status": row.status, "error": row.error,
        "campaignId": str(row.campaign_id) if row.campaign_id else None,
        "callbackCallId": str(row.callback_call_id) if row.callback_call_id else None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "completedAt": row.completed_at.isoformat() if row.completed_at else None,
    }


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise _err(503, "db_unavailable", "Language callbacks are temporarily unavailable")
    return factory


async def list_language_switch_requests(tenant_id: uuid.UUID, *, agent_id: str | None = None, status: str | None = "open",
                                        language: str | None = None) -> list[dict[str, Any]]:
    Item, _ = _models()
    query = select(Item).where(Item.tenant_id == tenant_id)
    if status == "open":
        query = query.where(Item.status.in_(("pending", "calling")))
    elif status and status != "all":
        if status not in STATUSES:
            raise _err(422, "invalid_status", "Unknown status")
        query = query.where(Item.status == status)
    if agent_id:
        query = query.where(Item.agent_id == agent_id)
    if language:
        query = query.where(Item.requested_language == (canonical_language(language) or language))
    async with _factory()() as session:
        rows = (await session.execute(query.order_by(Item.created_at.desc()).limit(500))).scalars().all()
        return [_public(r) for r in rows]


async def _owned_items(session, tenant_id: uuid.UUID, ids: list[uuid.UUID], *, lock: bool = False):
    Item, _ = _models()
    query = select(Item).where(Item.tenant_id == tenant_id, Item.id.in_(ids))
    return (await session.execute(query.with_for_update() if lock else query)).scalars().all()


async def update_language_switch_status(tenant_id: uuid.UUID, item_id: uuid.UUID, status: str) -> dict[str, Any]:
    if status not in ("pending", "done", "dismissed"):
        raise _err(422, "invalid_status", "Choose pending, done or dismissed")
    async with _factory()() as session:
        rows = await _owned_items(session, tenant_id, [item_id], lock=True)
        if not rows:
            raise _err(404, "not_found", "Language callback not found")
        row = rows[0]
        row.status, row.updated_at = status, _now()
        row.completed_at = _now() if status == "done" else None
        await session.commit()
        return _public(row)


async def language_readiness(agent: dict[str, Any], language: str) -> dict[str, Any]:
    """Can this agent call in ``language`` right now? Renders the brain for that pack to prove it."""
    from server.call.language_switch import is_supported_target, language_name

    code = canonical_language(language)
    label = language_name(code or language)
    if not code or not is_supported_target(code):
        return {"ready": False, "language": code or language, "code": "language_unavailable",
                "message": f"{label} isn't offered on this platform yet, so this contact can't be called in it."}
    if not agent.get("active_compiled_brain_version"):
        return {"ready": False, "language": code, "code": "brain_not_published",
                "message": "Publish this agent's script before calling."}
    agent_id = str(agent.get("agent_id") or agent.get("id") or "")
    try:
        from server.brain.compiled_brain_artifact import refresh_platform_sections
        from server.brain.compiled_brain_service import compiled_brain_service

        snapshot = await compiled_brain_service.get_active_for_agent(agent_id)
        # Build (compile on demand) the brain with the requested pack, exactly as the call will.
        await asyncio.to_thread(refresh_platform_sections, snapshot.get("compiled_text") or "", code)
    except ValueError as exc:
        return {"ready": False, "language": code, "code": "script_needs_review",
                "message": f"This agent's custom farewell or recording disclosure is written for another language. "
                           f"Review it for {label} in the agent's script, then call again. ({str(exc)[:120]})"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("language_switch.readiness_brain_failed kind=%s", type(exc).__name__)
        return {"ready": False, "language": code, "code": "brain_unavailable",
                "message": f"The agent's script could not be prepared in {label}. Try again shortly."}
    try:
        from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent

        stack = await saas_stack_override_for_agent(language_override_agent(agent, code))
        if str(stack.get("language") or code) != code:
            raise ValueError("language_not_applied")
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "language": code, "code": "voice_unavailable",
                "message": f"The agent's voice settings can't speak {label}. Choose a voice that supports it in the "
                           f"agent's voice settings. ({type(exc).__name__})"}
    return {"ready": True, "language": code, "code": "ready",
            "message": f"The agent's published script will run with the {label} language pack "
                       f"(speech recognition, voice and opening line in {label})."}


async def apply_call_language(agent: dict[str, Any], language: str) -> dict[str, Any]:
    """Outbound dial guard for a per-call language override."""
    from server.call.language_switch import is_supported_target, language_name

    code = canonical_language(language)
    if not code or not is_supported_target(code):
        raise _err(409, "language_unavailable", f"{language_name(code or language)} isn't offered on this platform.")
    return language_override_agent(agent, code)


async def preferred_language_for(tenant_id: uuid.UUID, phone: str) -> str | None:
    factory = get_session_factory()
    target = normalize_e164(phone)
    if factory is None or not target:
        return None
    try:
        _, Pref = _models()
        async with factory() as session:
            return (await session.execute(select(Pref.language).where(Pref.tenant_id == tenant_id,
                Pref.phone_e164 == target))).scalar_one_or_none()
    except Exception:  # noqa: BLE001 -- before migration 050 the preference simply isn't known.
        return None


async def apply_preferred_language(tenant_id: uuid.UUID, agent: dict[str, Any], phone: str) -> dict[str, Any]:
    """A remembered language leads the call only when the agent is already configured for it."""
    preferred = await preferred_language_for(tenant_id, phone)
    languages = [str(c) for c in (agent.get("languages") or []) if c]
    if not preferred or preferred not in languages or languages[:1] == [preferred]:
        return agent
    return language_override_agent(agent, preferred)


async def call_language_switch(principal: Any, item_id: uuid.UUID, *, from_e164: str | None = None) -> dict[str, Any]:
    """Call one contact back now: same agent, requested language, normal callback path."""
    from server.services.saas.call_callback_service import request_callback, resolve_workspace_agent
    from server.services.saas.tenant_guard import subscriber_workspace_tenant_id

    tenant_id = subscriber_workspace_tenant_id(principal)
    async with _factory()() as session:
        rows = await _owned_items(session, tenant_id, [item_id])
        if not rows:
            raise _err(404, "not_found", "Language callback not found")
        row = rows[0]
        if row.status in ("done", "dismissed"):
            raise _err(409, "already_closed", "This language callback is already closed.")
        item = _public(row)
    agent = await resolve_workspace_agent(item["agentId"], str(tenant_id))
    readiness = await language_readiness(agent, item["requestedLanguage"])
    if not readiness["ready"]:
        raise _err(409, readiness["code"], readiness["message"])
    request_id = f"ls:{item_id}:{uuid.uuid4().hex[:12]}"
    contact = {"call_language": item["requestedLanguage"], "language_switch_id": item["id"],
               **({"full_name": item["contactName"]} if item["contactName"] else {})}
    if item["callId"]:
        result = await request_callback(principal, call_id=item["callId"], to_e164=item["phone"], agent_id=item["agentId"],
                                        from_e164=from_e164, dial_request_id=request_id, mode="manual", contact=contact)
    else:
        from server.services.saas.telephony_orchestrator import subscriber_outbound

        result = await subscriber_outbound(principal, agent_id=item["agentId"], from_e164=from_e164,
                                           to_e164=item["phone"], dial_request_id=request_id, contact=contact)
    ok = bool(result.get("ok"))
    async with _factory()() as session:
        rows = await _owned_items(session, tenant_id, [item_id], lock=True)
        if rows:
            rows[0].status = "calling" if ok else rows[0].status
            rows[0].last_dial_request_id = request_id
            rows[0].error = None if ok else str(result.get("error") or "dial_failed")[:300]
            rows[0].updated_at = _now()
            await session.commit()
    return {"ok": ok, "itemId": str(item_id), "language": item["requestedLanguage"], "dialRequestId": request_id,
            "error": result.get("error"), "code": result.get("code")}


async def campaign_contacts_for(tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Group open items by agent as campaign contacts, each carrying its own call language."""
    async with _factory()() as session:
        rows = await _owned_items(session, tenant_id, ids)
    by_agent: dict[str, list[dict[str, Any]]] = {}
    skipped: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.status not in ("pending", "calling") or (row.agent_id, row.phone_e164) in seen:
            skipped.append(str(row.id))
            continue
        seen.add((row.agent_id, row.phone_e164))
        by_agent.setdefault(row.agent_id, []).append({
            "phone": row.phone_e164, **({"full_name": row.contact_name} if row.contact_name else {}),
            "call_language": row.requested_language, "language_switch_id": str(row.id),
        })
    skipped += [str(i) for i in ids if str(i) not in {str(r.id) for r in rows}]
    return by_agent, skipped


async def mark_campaign_items(tenant_id: uuid.UUID, campaign_id: str, item_ids: list[str]) -> None:
    async with _factory()() as session:
        rows = await _owned_items(session, tenant_id, [uuid.UUID(i) for i in item_ids], lock=True)
        for row in rows:
            row.status, row.campaign_id, row.updated_at, row.error = "calling", uuid.UUID(campaign_id), _now(), None
        await session.commit()


async def validate_campaign_languages(agent: dict[str, Any], contacts: list[dict[str, Any]]) -> None:
    """Campaign contacts may each carry ``call_language``; every one must be callable by this agent."""
    languages = {str(c.get("call_language") or "").strip() for c in contacts if str(c.get("call_language") or "").strip()}
    for language in sorted(languages):
        readiness = await language_readiness(agent, language)
        if not readiness["ready"]:
            raise _err(409, readiness["code"], readiness["message"])
    for contact in contacts:
        if str(contact.get("call_language") or "").strip():
            contact["call_language"] = canonical_language(contact["call_language"])
