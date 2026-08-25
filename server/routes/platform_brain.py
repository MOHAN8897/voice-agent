"""Platform brain admin routes — developer only (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.platform_brain_store import platform_brain_store
from server.config.env import get_settings

router = APIRouter()

REGRESSION_SCENARIOS = [
    {
        "id": "min_length",
        "label": "Minimum platform body length",
        "check": lambda body: len(body.strip()) >= 50,
        "message": "Body must be at least 50 characters",
    },
    {
        "id": "output_contract",
        "label": "Output contract present",
        "check": lambda body: "output" in body.lower(),
        "message": "Include explicit output / response contract language",
    },
    {
        "id": "memory_contract",
        "label": "Memory contract keywords",
        "check": lambda body: "memory" in body.lower() or "remember" in body.lower(),
        "message": "Reference memory projection or recall behavior",
    },
    {
        "id": "telugu_support",
        "label": "Telugu language guidance",
        "check": lambda body: "telugu" in body.lower() or "te-in" in body.lower(),
        "message": "Include Telugu / te-IN language behavior",
    },
]


class PlatformDraftBody(BaseModel):
    body: str = Field(..., min_length=10)


class ActivateBody(BaseModel):
    version_id: str | None = None
    body: str | None = None
    reason: str = Field("activation", min_length=3, max_length=200)
    skip_regression: bool = False


class RegressionBody(BaseModel):
    body: str = Field(..., min_length=10)


@router.get("/api/platform-brain")
async def get_platform_brain(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    active = await platform_brain_store.get_active()
    return {
        "active": {
            "version_id": active["version_id"],
            "status": active["status"],
            "preview": platform_brain_store.redacted_preview(active["body"]),
        }
    }


@router.get("/api/platform-brain/versions")
async def list_platform_versions(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    versions = await platform_brain_store.list_versions()
    return {"versions": versions}


@router.get("/api/platform-brain/budget-cache")
async def platform_brain_budget(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    s = get_settings()
    active = await platform_brain_store.get_active()
    body_len = len(active.get("body") or "")
    budget = s.brain_prompt_budget_tokens
    return {
        "brain_prompt_budget_tokens": budget,
        "platform_body_chars": body_len,
        "estimated_tokens": max(1, body_len // 4),
        "budget_utilization_pct": round(min(100, (body_len // 4) / max(budget, 1) * 100), 1),
        "prompt_caching_enabled": True,
        "note": "OpenAI gpt-5.6 family supports prompt caching on stable platform prefix",
    }


@router.get("/api/platform-brain/draft")
async def get_platform_draft(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    draft = await platform_brain_store.get_draft()
    if draft is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "No platform brain draft"}},
        )
    return {
        "draft": {
            "version_id": draft["version_id"],
            "status": draft["status"],
            "body": draft["body"],
            "created_by": draft.get("created_by"),
        }
    }


@router.put("/api/platform-brain/draft")
async def save_platform_draft(body: PlatformDraftBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    draft = await platform_brain_store.save_draft(body.body)
    return {"ok": True, "draft": {"version_id": draft["version_id"], "status": draft["status"]}}


@router.post("/api/platform-brain/validate")
async def validate_platform_brain(body: PlatformDraftBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    issues = []
    if len(body.body.strip()) < 50:
        issues.append({"severity": "blocking", "code": "too_short", "message": "Platform brain body too short"})
    if "OUTPUT" not in body.body.upper() and "output" not in body.body.lower():
        issues.append(
            {
                "severity": "warning",
                "code": "missing_output_contract",
                "message": "Consider including explicit output contract instructions",
            }
        )
    return {"ok": not any(i["severity"] == "blocking" for i in issues), "issues": issues}


@router.post("/api/platform-brain/regression-check")
async def regression_check(body: RegressionBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    results = []
    passed = 0
    for scenario in REGRESSION_SCENARIOS:
        ok = scenario["check"](body.body)
        if ok:
            passed += 1
        results.append(
            {
                "id": scenario["id"],
                "label": scenario["label"],
                "passed": ok,
                "message": scenario["message"] if not ok else "OK",
            }
        )
    return {
        "ok": passed == len(REGRESSION_SCENARIOS),
        "passed": passed,
        "total": len(REGRESSION_SCENARIOS),
        "scenarios": results,
    }


@router.post("/api/platform-brain/activate")
async def activate_platform_brain(payload: ActivateBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    if payload.body and not payload.skip_regression:
        reg = await regression_check(RegressionBody(body=payload.body), session)
        if not reg["ok"]:
            return {
                "ok": False,
                "error": {
                    "code": "regression_failed",
                    "message": "Regression scenarios must pass before activation",
                    "scenarios": reg["scenarios"],
                },
            }
    if payload.body:
        issues = []
        if len(payload.body.strip()) < 50:
            issues.append({"severity": "blocking", "code": "too_short", "message": "Platform brain body too short"})
        if any(i["severity"] == "blocking" for i in issues):
            return {"ok": False, "error": {"code": "validation_error", "message": "Validation failed", "issues": issues}}

    if payload.version_id:
        activated = await platform_brain_store.activate(payload.version_id)
    elif payload.body:
        draft = await platform_brain_store.save_draft(payload.body)
        activated = await platform_brain_store.activate(draft["version_id"])
    else:
        active = await platform_brain_store.get_active()
        activated = await platform_brain_store.activate(active["version_id"])

    from server.brain.agent_service import agent_service

    default_id = await agent_service.resolve_default_agent_id()
    snapshot = await compiled_brain_service.compile_for_agent(default_id)
    return {
        "ok": True,
        "activated": activated["version_id"],
        "compiled": snapshot["compiled_version"],
        "reason": payload.reason,
        "actor": session.subject,
    }


@router.post("/api/platform-brain/{version_id}/rollback")
async def rollback_platform_brain(version_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.platform_brain")
    try:
        activated = await platform_brain_store.rollback(version_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Version {version_id} not found"}},
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "validation_error", "message": str(e)}},
        ) from e

    from server.brain.agent_service import agent_service

    default_id = await agent_service.resolve_default_agent_id()
    snapshot = await compiled_brain_service.compile_for_agent(default_id)
    return {
        "ok": True,
        "rolled_back_to": activated["version_id"],
        "compiled": snapshot["compiled_version"],
        "actor": session.subject,
    }
