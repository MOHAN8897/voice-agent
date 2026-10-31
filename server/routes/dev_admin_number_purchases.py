"""Platform admin "Number purchases": every purchase, why it failed, and the fix.

Read endpoints need ``dev.admin.numbers``; retry/refund move money or carrier
state and need ``dev.admin.billing`` plus a written reason (audited).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.services.saas import number_purchase_admin as svc
from server.services.saas.admin_audit import record_admin_action

router = APIRouter(tags=["dev-admin-number-purchases"])

MIN_REASON = 8


def _require_db() -> None:
    if get_session_factory() is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "database_required", "message": "Database required"}})


def _pid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Purchase not found."}}) from None


class ReasonBody(BaseModel):
    reason: str = Field("", max_length=500)


def _reason(body: ReasonBody) -> str:
    reason = (body.reason or "").strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "reason_required", "message": f"Write a reason of at least {MIN_REASON} characters."}},
        )
    return reason


@router.get("/api/dev/admin/number-purchases")
async def list_number_purchases(
    status: str | None = Query(None, max_length=32),
    q: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    return await svc.list_admin_purchases(status=status, q=q, limit=limit, offset=offset)


@router.get("/api/dev/admin/number-purchases/health")
async def number_purchases_health(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    return await svc.purchases_health()


@router.get("/api/dev/admin/number-purchases/refusals")
async def number_purchase_refusals(
    platformOnly: bool = False,
    limit: int = Query(100, ge=1, le=500),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    return await svc.list_refusals(platform_only=platformOnly, limit=limit)


@router.get("/api/dev/admin/number-purchases/{purchase_id}")
async def number_purchase_detail(purchase_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.admin.numbers")
    _require_db()
    item = await svc.purchase_detail(_pid(purchase_id))
    if item is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Purchase not found."}})
    return item


async def _act(kind: str, purchase_id: str, body: ReasonBody, session: SessionData) -> dict:
    require_permission(session, "dev.admin.billing")
    _require_db()
    reason = _reason(body)
    pid = _pid(purchase_id)
    try:
        result = await (svc.retry_purchase(pid) if kind == "retry" else svc.refund_purchase(pid))
    except svc.PurchaseAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": {"code": exc.code, "message": exc.message}}) from None
    await record_admin_action(
        actor=session.subject,
        action="purchase.retry_provision" if kind == "retry" else "purchase.refund",
        resource_type="number_purchase",
        resource_id=str(pid),
        tenant_id=result.get("tenantId"),
        payload={"reason": reason, **{k: v for k, v in result.items() if k != "tenantId"}},
    )
    return {k: v for k, v in result.items() if k != "tenantId"}


@router.post("/api/dev/admin/number-purchases/{purchase_id}/retry")
async def retry_number_purchase(purchase_id: str, body: ReasonBody, session: SessionData = Depends(require_dev_session)):
    return await _act("retry", purchase_id, body, session)


@router.post("/api/dev/admin/number-purchases/{purchase_id}/refund")
async def refund_number_purchase(purchase_id: str, body: ReasonBody, session: SessionData = Depends(require_dev_session)):
    return await _act("refund", purchase_id, body, session)
