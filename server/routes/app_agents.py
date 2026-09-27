"""Subscriber agent onboarding helpers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.brain.agent_service import agent_service
from server.services.saas.agent_onboarding_compose import compose_agent_onboarding
from server.services.saas.employee_brain_build import publish_saas_employee_brain
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)

router = APIRouter()


class ComposeOnboardingBody(BaseModel):
    name: str = Field("", max_length=255)
    role: str = Field("Customer Support", max_length=120)
    language: str = Field("en-IN", max_length=32)
    businessSummary: str = Field("", max_length=4000)
    goals: str = Field("", max_length=2000)
    notes: str = Field("", max_length=2000)
    brief: str = Field("", max_length=6000)
    mode: str = Field("instant_lead", max_length=40)
    industry: str = Field("", max_length=120)
    naturalSpokenStyle: bool = False


class BuildEmployeeBody(BaseModel):
    brief: str = Field(..., min_length=8, max_length=6000)
    language: str = Field("en-IN", max_length=32)
    mode: str = Field("instant_lead", max_length=40)
    industry: str = Field("", max_length=120)
    naturalSpokenStyle: bool = False
    employeeName: str = Field("", max_length=255)


@router.post("/api/app/agents/compose-onboarding")
async def compose_onboarding(
    body: ComposeOnboardingBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.agents.write")
    result = await compose_agent_onboarding(
        name=body.name.strip(),
        role=body.role.strip(),
        language=body.language.strip(),
        business_summary=body.businessSummary.strip(),
        goals=body.goals.strip(),
        extra_notes=body.notes.strip(),
        brief=body.brief.strip(),
        mode=body.mode.strip() or "instant_lead",
        industry=body.industry.strip(),
        telugu_enhance=body.naturalSpokenStyle,
        natural_spoken_style=body.naturalSpokenStyle,
    )
    return {"ok": True, **result}


@router.post("/api/app/agents/build-employee")
async def build_employee(
    body: BuildEmployeeBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Brief → dev-panel script compiler → single Calling script section → cached brain."""
    require_subscriber_permission(principal, "app.agents.write")
    lang = (body.language.strip() or "en-IN")
    tenant_id = str(subscriber_workspace_tenant_id(principal))

    voice_config = {
        "realtimeVoice": "marin",
        "voiceId": "marin",
        "speed": 1.0,
        "language": lang,
        "turnDetection": "semantic_vad",
        "noiseReduction": "far_field",
    }

    from server.services.saas.employee_brain_build import compile_brief_for_employee

    try:
        _compiled, script_result, variables = await compile_brief_for_employee(
            brief=body.brief.strip(),
            language=lang,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "script_compile_failed", "message": str(e)}},
        )

    display_name = (
        body.employeeName.strip()
        or (script_result.agent_name or "").strip()
        or "AI Employee"
    )[:255]

    agent = await agent_service.create_agent(
        name=display_name,
        tenant_id=tenant_id,
        languages=[lang],
    )
    agent_id = str(agent.get("agent_id") or agent.get("id") or "")
    if not agent_id:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "create_failed", "message": "Agent not created"}},
        )

    try:
        published = await publish_saas_employee_brain(
            agent_id,
            brief=body.brief.strip(),
            language=lang,
            voice_config=voice_config,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "publish_failed", "message": str(e)}},
        )

    return {
        "ok": True,
        "agent": agent,
        "agentId": agent_id,
        "script": published.get("script"),
        "variables": published.get("variables"),
        "source": "agent_script_compiler",
    }
