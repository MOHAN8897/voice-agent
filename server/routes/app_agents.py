"""Subscriber agent onboarding helpers."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.brain.agent_service import AgentBuildRequestConflict, agent_service
from server.brain.brief_contract import BriefValidationError, normalize_generation_config
from server.brain.employee_script_pipeline import (
    ClarificationAnswer,
    GenerationStageError,
    analyze_employee_brief,
    clarification_response,
)
from server.brain.script_entities import strip_entity_tags_section
from server.config.constants import normalize_supported_language
from server.routes.agents import _subscriber_agent
from server.services.saas import platform_languages
from server.services.saas.agent_onboarding_compose import compose_agent_onboarding
from server.services.saas.employee_brain_build import publish_saas_employee_brain
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.utils.errors import AppError, ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)

# Matches Agent.default_tier and AgentService.create_agent; creation never
# negotiates a tier, so readiness must be checked against this one.
CREATED_AGENT_TIER = "medium"


async def _profile_language(environment: str) -> dict:
    from server.services.saas.voice_stack_profiles import profile_language_support

    return await profile_language_support(environment, CREATED_AGENT_TIER)


@router.get("/api/app/agents/languages")
async def available_languages():
    """Languages the creation UI may offer.

    Admin-configurable, so the picker is never a hardcoded list in the bundle.
    Entries the default calling tier cannot serve are returned separately rather
    than offered and rejected later.
    """
    from server.services.dev_runtime import effective_app_environment

    options = platform_languages.language_options()
    support = await _profile_language(effective_app_environment())
    supported = set(support["supportedLanguages"])
    if support["configured"] and supported:
        offered = [option for option in options if option["code"] in supported]
        unavailable = [option for option in options if option["code"] not in supported]
    else:
        offered, unavailable = options, []
    default = offered[0]["code"] if offered else ""
    return {
        "languages": offered,
        "default": default,
        "tier": support["tier"] if support["configured"] else None,
        "unavailableOnTier": unavailable,
    }


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
    agentRole: str = Field("", max_length=120)
    callDirection: str = Field("", max_length=20)
    requestId: uuid.UUID | None = None
    retryFailed: bool = False
    clarificationAnswers: list[ClarificationAnswer] = Field(default_factory=list, max_length=20)


def _generation_settings(body: BuildEmployeeBody) -> dict:
    return {
        "employeeName": body.employeeName.strip(), "agentRole": body.agentRole.strip(),
        "callDirection": body.callDirection.strip(), "mode": body.mode.strip(),
        "industry": body.industry.strip(), "naturalSpokenStyle": body.naturalSpokenStyle,
    }


@router.post("/api/app/agents/analyze-brief")
async def analyze_brief(
    body: BuildEmployeeBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """Read-only clarification: never creates an agent or publishes a draft."""
    require_subscriber_permission(principal, "app.agents.write")
    subscriber_workspace_tenant_id(principal)
    # Retired codes such as "en-GB" resolve to the pack that actually speaks them.
    language = normalize_supported_language(body.language.strip() or "en-IN")
    if not platform_languages.is_enabled(language):
        raise HTTPException(status_code=400, detail={"error": {"code": "language_not_enabled", "message": "Choose an available spoken language."}})
    try:
        extracted = await analyze_employee_brief(brief=body.brief.strip(), language=language,
            generation_config=_generation_settings(body), answers=body.clarificationAnswers)
        return clarification_response(extracted)
    except BriefValidationError as exc:
        raise HTTPException(status_code=422, detail={"error": exc.to_dict()}) from exc
    except GenerationStageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.to_public_dict()},
            headers={"Retry-After": "10"} if exc.transient else None,
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"error": {"code": "brief_analysis_unavailable",
            "message": "We could not check the brief right now. Your answers are kept; please try again."}}) from exc


@router.post("/api/app/agents/compose-onboarding")
async def compose_onboarding(
    body: ComposeOnboardingBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.agents.write")
    result = await compose_agent_onboarding(
        name=body.name.strip(),
        role=body.role.strip(),
        language=normalize_supported_language(body.language.strip() or "en-IN"),
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
    # Legacy clients may still send a retired code such as "en-GB"; it resolves to
    # the English locale the live stack speaks, never to a different language.
    lang = normalize_supported_language(body.language.strip() or "en-IN")
    # The picker only offers enabled languages; enforce it here too, or a crafted
    # request could create an agent in a language the platform has switched off.
    # Existing agents keep working — this only gates creation.
    if not platform_languages.is_enabled(lang):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "language_not_enabled",
                    "message": f"{lang} is not available for new agents right now.",
                }
            },
        )
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_stack_profiles import VoiceProfileError, validate_agent_language_for_tier

    try:
        await validate_agent_language_for_tier(effective_app_environment(), CREATED_AGENT_TIER, lang)
    except VoiceProfileError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": str(exc), **exc.details}},
        ) from exc
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

    generation_config = _generation_settings(body)
    claimed_agent = None
    if body.requestId is not None:
        try:
            generation_config = normalize_generation_config(generation_config)
            fingerprint = hashlib.sha256(json.dumps({
                "brief": body.brief.strip(), "language": lang,
                "generationConfig": generation_config,
                "clarificationAnswers": [item.model_dump() for item in body.clarificationAnswers],
            }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            claim = await agent_service.claim_build_request(
                request_id=str(body.requestId), fingerprint=fingerprint, tenant_id=tenant_id,
                name=body.employeeName.strip() or "Unfinished agent", language=lang,
                retry_failed=bool(body.retryFailed),
            )
        except BriefValidationError as exc:
            raise HTTPException(status_code=422, detail={"error": exc.to_dict()}) from exc
        except AgentBuildRequestConflict as exc:
            raise HTTPException(status_code=409, detail={"error": {"code": exc.code, "message": str(exc)}}) from exc
        claimed_agent = claim["agent"]
        if not claim["created"] and not claim.get("resumed"):
            if claim.get("state") == "completed":
                response = claim["response"]
                return {**response, "agent": _subscriber_agent(response.get("agent") or {})}
            if claim.get("state") == "failed":
                raise HTTPException(status_code=int(claim.get("status_code") or 502), detail={"error": claim.get("error")})
            raise HTTPException(status_code=409, detail={"error": {
                "code": "creation_in_progress", "agentId": claimed_agent["agent_id"],
                "message": "This agent creation is already in progress. Wait before retrying; the same request will not create another agent.",
            }})

    async def record_failed_request(error: dict, status_code: int) -> None:
        if claimed_agent is not None:
            error["agentId"] = claimed_agent["agent_id"]
            error["draftRetained"] = True
            error["message"] = str(error.get("message") or "Creation failed.") + " An unfinished agent remains in your agent list; review or remove it before starting a new creation request."
            try:
                await agent_service.finish_build_request(claimed_agent["agent_id"], tenant_id=tenant_id, error=error, status_code=status_code)
            except Exception:  # noqa: BLE001 - retain the failed draft if recording its error fails.
                error["recoveryRequired"] = True

    try:
        answer_options = {"answers": body.clarificationAnswers} if body.clarificationAnswers else {}
        artifact = await compile_brief_for_employee(
            brief=body.brief.strip(),
            language=lang,
            generation_config=generation_config,
            **answer_options,
        )
    except BriefValidationError as exc:
        error = exc.to_dict()
        await record_failed_request(error, 422)
        raise HTTPException(status_code=422, detail={"error": error}) from exc
    except GenerationStageError as exc:
        error = exc.to_public_dict()
        logger.warning(
            "agent.generation_failed agent_id=%s stage=%s transient=%s correlation_id=%s code=%s",
            (claimed_agent or {}).get("agent_id"), exc.stage, exc.transient, exc.correlation_id, error["code"],
        )
        await record_failed_request(error, exc.status_code)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": error},
            headers={"Retry-After": "10"} if exc.transient else None,
        ) from exc
    except Exception as exc:
        error = {"code": "script_compile_failed", "message": "Script generation failed. Please try again."}
        await record_failed_request(error, 502)
        raise HTTPException(
            status_code=502,
            detail={"error": error},
        ) from exc
    _compiled, script_result, _variables = artifact

    display_name = (
        body.employeeName.strip()
        or (script_result.agent_name or "").strip()
        or "AI Employee"
    )[:255]

    if claimed_agent is None:
        agent = await agent_service.create_agent(name=display_name, tenant_id=tenant_id, languages=[lang])
    else:
        try:
            agent = await agent_service.patch_agent(claimed_agent["agent_id"], {"name": display_name}, tenant_id=tenant_id)
            if not str(agent.get("agent_id") or agent.get("id") or ""):
                raise ValueError("Claimed agent id is missing")
        except Exception as exc:
            error = {"code": "create_failed", "message": "The generated script could not be attached to its agent. An unfinished draft was retained for review."}
            await record_failed_request(error, 502)
            raise HTTPException(status_code=502, detail={"error": error}) from exc
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
            generation_config=generation_config,
            compiled_artifact=artifact,
        )
    except Exception as exc:
        if isinstance(exc, BriefValidationError):
            publication_error, publication_status = exc.to_dict(), 422
        elif isinstance(exc, AppError) and exc.code in (ErrorCode.VALIDATION_ERROR, ErrorCode.CONFLICT):
            publication_error, publication_status = {"code": exc.code.value, "message": exc.user_message}, exc.status_code
        else:
            publication_error, publication_status = {"code": "publish_failed", "message": "The script could not be published. Please try again."}, 502
        if claimed_agent is not None:
            await record_failed_request(publication_error, publication_status)
            raise HTTPException(status_code=publication_status, detail={"error": publication_error}) from exc
        # This ID was created by this request and has never been returned to the
        # caller. Cleanup must still enforce the same workspace ownership.
        cleanup_failed = False
        try:
            await agent_service.delete_agent(agent_id, tenant_id=tenant_id)
        except Exception:  # noqa: BLE001 - cleanup must not hide the publication failure.
            cleanup_failed = True
        error = {**publication_error, "cleanupFailed": cleanup_failed}
        if cleanup_failed:
            error["agentId"] = agent_id
            error["message"] += " An unfinished agent remains; remove it before retrying."
        raise HTTPException(
            status_code=publication_status,
            detail={"error": error},
        ) from exc

    response = {
        "ok": True,
        "agent": _subscriber_agent(agent),
        "agentId": agent_id,
        # Entity tags are the compiler/runtime contract, not part of the document the
        # customer reads. They stay in the stored section and the compiled brain.
        "script": strip_entity_tags_section(published.get("script") or ""),
        "variables": published.get("variables"),
        "source": "agent_script_compiler",
        "generation": published.get("generation") or script_result.to_dict(),
    }
    if claimed_agent is not None:
        try:
            completed = await agent_service.finish_build_request(agent_id, tenant_id=tenant_id, response=response)
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"error": {
                "code": "creation_recovery_required", "agentId": agent_id,
                "message": "The agent was published, but creation confirmation could not be saved. Open this agent before retrying.",
            }}) from exc
        result = completed or response
        return {**result, "agent": _subscriber_agent(result.get("agent") or {})}
    return response


@router.get("/api/app/agents/{agent_id}/call-warnings")
async def agent_call_warnings_read(agent_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Settings the agent's recent calls show need attention (read-only)."""
    from server.services.saas.agent_call_warnings import agent_call_warnings
    from server.services.saas.tenant_guard import load_agent_for_tenant

    require_subscriber_permission(principal, "app.calls.read")
    tenant_id = subscriber_workspace_tenant_id(principal)
    agent = await load_agent_for_tenant(agent_id, tenant_id)
    return await agent_call_warnings(str(tenant_id), agent)
