"""
Instructions routes — single brain prompt editing; legacy behaviour/business still supported.
"""
from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from server.agent.brain_prompt_composer import (
    BUDGET_MAX_TOKENS,
    BUDGET_MIN_TOKENS,
    CACHE_MIN_TOKENS,
    MAX_AGENT_BRIEF_CHARS,
    MAX_AGENT_BRIEF_WORDS,
    MAX_AGENT_SCRIPT_CHARS,
    MAX_AGENT_SCRIPT_WORDS,
    MAX_BEHAVIOUR_CHARS,
    MAX_BEHAVIOUR_WORDS,
    MAX_BRAIN_PROMPT_CHARS,
    MAX_BRAIN_PROMPT_WORDS,
    MAX_BUSINESS_CHARS,
    MAX_BUSINESS_WORDS,
    MEMORY_HEADROOM_TOKENS,
    RECOMMENDED_AGENT_BRIEF_WORDS,
    RECOMMENDED_AGENT_SCRIPT_WORDS,
    RECOMMENDED_BEHAVIOUR_WORDS,
    RECOMMENDED_BUSINESS_WORDS,
    PromptBudgetExceeded,
    PromptSectionTooLong,
    estimate_tokens,
    sanitize_agent_script,
    validate_user_section,
)
from server.agent.instruction_store import instruction_store
from server.agent.session_memory import session_memory
from server.config.env import get_settings, ConfigError
from server.prompts.brain_prompt import get_factory_brain_prompt
from server.services.brain_budget import resolve_brain_budget
from server.services.prompt_cache_key import cache_eligible

router = APIRouter()


def _normalize_call_direction(raw: str | None) -> str | None:
    d = str(raw or "").strip().lower()
    if not d:
        return None
    return "inbound" if d in ("inbound", "incoming", "in") else "outbound"


def _brief_with_compile_hints(
    brief: str,
    *,
    direction: str | None = None,
    role: str | None = None,
) -> str:
    lines: list[str] = []
    if direction:
        lines.append(f"Call direction: {direction}.")
    if role and role.strip():
        lines.append(f"Primary role on this call: {role.strip()}.")
    body = (brief or "").strip()
    if not lines:
        return body
    return "\n".join(lines) + ("\n\n" + body if body else "")


def _limits() -> tuple[int, int, int]:
    try:
        _ = get_settings()
    except ConfigError:
        pass
    return MAX_BEHAVIOUR_CHARS, MAX_BUSINESS_CHARS, MAX_BRAIN_PROMPT_CHARS


class SaveRequest(BaseModel):
    sessionId: str = Field("default", max_length=100)
    brainPrompt: str | None = Field(None, description="Single composed brain prompt (advanced)")
    agentBrief: str | None = Field(None, description="Short natural-language agent brief — expanded into calling script")
    agentScript: str | None = Field(
        None,
        max_length=MAX_AGENT_SCRIPT_CHARS,
        description="User-edited calling script — saved without regenerating from the brief",
    )
    behaviourInstructions: str | None = Field(None, description="Legacy: HOW the agent should respond")
    businessInstructions: str | None = Field(None, description="Legacy: business knowledge")
    instructions: str | None = Field(None, max_length=MAX_BEHAVIOUR_CHARS)
    responseStyle: str | None = Field(None, max_length=100)
    brainPromptBudgetTokens: int | None = Field(None, description="Optional budget override for validation")
    language_code: str | None = Field("te-IN", max_length=16)
    callEndPolicy: dict | None = None
    reassembleOnly: bool = False
    compileFromBrief: bool = Field(
        False,
        description="When true with agentBrief, replace the entire calling script (ignore agentScript body).",
    )
    callDirection: str | None = Field(
        None,
        max_length=16,
        description="outbound | inbound — shapes platform workflow and entity tags when compiling from brief.",
    )
    agentRole: str | None = Field(
        None,
        max_length=48,
        description="sales | support | … — hints role when compiling from brief.",
    )


@router.get("/api/instructions/default")
async def get_default_brain_prompt():
    """Factory default brain prompt for the UI editor."""
    prompt = get_factory_brain_prompt()
    est = estimate_tokens(prompt)
    return {
        "brainPrompt": prompt,
        "estimatedTokens": est,
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "budgetMinTokens": BUDGET_MIN_TOKENS,
        "budgetMaxTokens": BUDGET_MAX_TOKENS,
        "maxWords": MAX_BRAIN_PROMPT_WORDS,
        "cacheEligible": cache_eligible(est),
        "maxChars": MAX_BRAIN_PROMPT_CHARS,
    }


@router.post("/api/instructions")
async def save_instructions(body: SaveRequest):
    b_max, z_max, p_max = _limits()
    budget = body.brainPromptBudgetTokens or resolve_brain_budget(body.sessionId)
    budget = max(BUDGET_MIN_TOKENS, min(BUDGET_MAX_TOKENS, int(budget)))

    from server.call.call_end_policy import default_call_end_policy, normalize_call_end_policy
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(body.language_code)
    policy = normalize_call_end_policy(body.callEndPolicy, language=lang)
    compiler_sections = None

    try:
        if body.compileFromBrief and body.agentBrief is not None:
            from server.brain.agent_script_compiler import (
                build_compiler_sections,
                compile_agent_from_brief,
            )

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            prev_compiled = prev_meta.get("brainPrompt") if prev_meta.get("compiledVersion") else None
            if body.callEndPolicy is None:
                policy = normalize_call_end_policy(prev_meta.get("callEndPolicy"), language=lang)
            compile_direction = _normalize_call_direction(body.callDirection)
            compile_brief = _brief_with_compile_hints(
                body.agentBrief,
                direction=compile_direction,
                role=body.agentRole,
            )
            try:
                compiled, script_result, raw_est, _compiled_est, effective_budget = await compile_agent_from_brief(
                    brief=compile_brief,
                    language=lang,
                    style=body.responseStyle,
                    budget_tokens=budget,
                    previous_compiled=prev_compiled,
                    call_end_policy=policy,
                    interpret_brief=True,
                    direction=compile_direction,
                )
            except (PromptSectionTooLong, PromptBudgetExceeded):
                raise
            except Exception as exc:
                from server.utils.logger import logger

                logger.error(
                    f"[AGENT_SCRIPT] compile failed, deterministic fallback: {type(exc).__name__}: {str(exc)[:240]}"
                )
                compiled, script_result, raw_est, _compiled_est, effective_budget = await compile_agent_from_brief(
                    brief=compile_brief,
                    language=lang,
                    style=body.responseStyle,
                    budget_tokens=budget,
                    previous_compiled=prev_compiled,
                    call_end_policy=policy,
                    use_llm=False,
                    interpret_brief=True,
                    direction=compile_direction,
                )
            budget = effective_budget
            compiler_sections = build_compiler_sections(
                user_script=script_result.agent_script,
                platform_call_rules=script_result.platform_call_rules,
                compiled_brain=compiled,
                language=lang,
                style=body.responseStyle,
                call_end_policy=policy,
            )
            saved = instruction_store.save_agent_script(
                body.sessionId,
                body.agentBrief,
                script_result.agent_script,
                script_result.response_style or body.responseStyle,
                compiled_brain=compiled,
                optimizer_report=script_result.to_dict(),
                source_checksum=script_result.source_checksum,
                language=lang,
                budget_tokens=budget,
                raw_token_estimate=raw_est,
                call_end_policy=policy,
            )
        elif body.reassembleOnly:
            from server.brain.agent_script_compiler import reassemble_brain_from_script

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            lang = normalize_compile_language(body.language_code or prev_meta.get("language"))
            policy = normalize_call_end_policy(
                body.callEndPolicy if body.callEndPolicy is not None else prev_meta.get("callEndPolicy"),
                language=lang,
            )
            policy = policy or default_call_end_policy(lang)
            script = (prev_meta.get("agentScript") or "").strip()
            compiled = None
            est = int(prev_meta.get("estimatedTokens") or 0)
            if script:
                opt = prev_meta.get("optimizerReport") if isinstance(prev_meta.get("optimizerReport"), dict) else {}
                _script, compiled = reassemble_brain_from_script(
                    script=script,
                    language=lang,
                    style=body.responseStyle or prev_meta.get("style"),
                    call_end_policy=policy,
                    platform_call_rules=str(opt.get("platform_call_rules") or ""),
                    agent_name=str(opt.get("agent_name") or ""),
                    role=str(opt.get("detected_role") or "other"),
                )
                est = estimate_tokens(compiled)
                if est > budget and est <= BUDGET_MAX_TOKENS:
                    budget = est
            saved = instruction_store.patch_call_end_policy(
                body.sessionId,
                policy,
                language=lang,
                compiled_brain=compiled,
                estimated_tokens=est or None,
                budget_tokens=budget,
            )
        elif body.agentScript is not None and not (body.compileFromBrief and body.agentBrief):
            from server.brain.agent_script_compiler import (
                build_compiler_sections,
                reassemble_brain_from_script,
                validate_agent_script,
            )
            from server.brain.script_entities import regenerate_calling_script_from_brief, script_conflicts_with_brief

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            lang = normalize_compile_language(body.language_code or prev_meta.get("language"))
            policy = normalize_call_end_policy(
                body.callEndPolicy if body.callEndPolicy is not None else prev_meta.get("callEndPolicy"),
                language=lang,
            )
            policy = policy or default_call_end_policy(lang)
            script = sanitize_agent_script(body.agentScript)
            brief = body.agentBrief if body.agentBrief is not None else str(prev_meta.get("agentBrief") or "")
            if brief.strip() and script_conflicts_with_brief(script, brief, language=lang):
                prev_compiled = prev_meta.get("brainPrompt") if prev_meta.get("compiledVersion") else None
                compiled, script, script_result = await regenerate_calling_script_from_brief(
                    brief,
                    language=lang,
                    style=body.responseStyle or prev_meta.get("style"),
                    budget_tokens=budget,
                    call_end_policy=policy,
                    previous_compiled=prev_compiled,
                )
                est = estimate_tokens(compiled)
                if est > budget and est <= BUDGET_MAX_TOKENS:
                    budget = est
                compiler_sections = build_compiler_sections(
                    user_script=script,
                    platform_call_rules=script_result.platform_call_rules,
                    compiled_brain=compiled,
                    language=lang,
                    style=body.responseStyle,
                    call_end_policy=policy,
                )
                saved = instruction_store.save_agent_script(
                    body.sessionId,
                    brief,
                    script,
                    script_result.response_style or body.responseStyle,
                    compiled_brain=compiled,
                    optimizer_report=script_result.to_dict(),
                    source_checksum=script_result.source_checksum,
                    language=lang,
                    budget_tokens=budget,
                    raw_token_estimate=int(prev_meta.get("rawTokenEstimate") or est),
                    call_end_policy=policy,
                )
            else:
                from server.brain.script_entities import (
                    backfill_entity_tags_in_script,
                    entities_have_values,
                    parse_entity_tags,
                    with_entity_tags_section,
                )
                from server.prompts.conversation_policy import infer_call_direction

                script_direction = infer_call_direction(brief or script)
                entity_tags = parse_entity_tags(script)
                if entities_have_values(entity_tags):
                    script = with_entity_tags_section(script, entity_tags)
                else:
                    script = backfill_entity_tags_in_script(
                        script,
                        brief=brief,
                        language=lang,
                        direction=script_direction,
                    )
                    entity_tags = parse_entity_tags(script)
                validate_user_section(
                    "Agent script",
                    script,
                    word_limit=MAX_AGENT_SCRIPT_WORDS,
                    char_limit=MAX_AGENT_SCRIPT_CHARS,
                )
                if not script:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": {
                                "code": "validation_error",
                                "message": "Calling script is empty — create an agent script first, then edit it.",
                            }
                        },
                    )
                opt = prev_meta.get("optimizerReport") if isinstance(prev_meta.get("optimizerReport"), dict) else {}
                from server.brain.agent_script_compiler import _platform_call_rules
                from server.prompts.agent_voice_rules import is_native_english
                from server.prompts.conversation_policy import infer_agent_role, infer_call_direction

                agent_name = (entity_tags.get("agent_name") or "").strip()
                if not agent_name:
                    ident_match = re.search(
                        r"(?is)---\s*AGENT IDENTITY\s*---\s*\n.{0,120}?\bYou are\s+([A-Za-z][A-Za-z'\-]{1,23})\b",
                        script,
                    )
                    agent_name = (ident_match.group(1) if ident_match else "") or str(opt.get("agent_name") or "")
                role = infer_agent_role(f"{brief}\n{script}", llm_role=str(opt.get("detected_role") or ""))
                direction = infer_call_direction(brief or script)
                platform_rules = _platform_call_rules(
                    agent_name=agent_name or ("Alex" if is_native_english(lang) else "Priya"),
                    role=role,
                    direction=direction,
                    language=lang,
                )
                style_val = body.responseStyle or prev_meta.get("style")
                _script, compiled = reassemble_brain_from_script(
                    script=script,
                    language=lang,
                    style=style_val,
                    call_end_policy=policy,
                    platform_call_rules=platform_rules,
                    agent_name=agent_name,
                    role=role,
                )
                est = estimate_tokens(compiled)
                if est > budget and est <= BUDGET_MAX_TOKENS:
                    budget = est
                warnings = validate_agent_script(script, brief=brief, agent_name=agent_name)
                report = dict(opt)
                report["user_edited"] = True
                report["script_warnings"] = warnings
                report["agent_name"] = agent_name
                report["detected_role"] = role
                report["platform_call_rules"] = platform_rules
                compiler_sections = build_compiler_sections(
                    user_script=script,
                    platform_call_rules=platform_rules,
                    compiled_brain=compiled,
                    language=lang,
                    style=style_val,
                    call_end_policy=policy,
                )
                source_checksum = hashlib.sha256(
                    f"{brief}\n{script}\n{lang}\n{style_val or ''}".encode("utf-8")
                ).hexdigest()
                saved = instruction_store.save_agent_script(
                    body.sessionId,
                    brief,
                    script,
                    style_val,
                    compiled_brain=compiled,
                    optimizer_report=report,
                    source_checksum=source_checksum,
                    language=lang,
                    budget_tokens=budget,
                    raw_token_estimate=int(prev_meta.get("rawTokenEstimate") or est),
                    call_end_policy=policy,
                )
        elif body.brainPrompt is not None:
            if len(body.brainPrompt) > p_max:
                raise HTTPException(
                    status_code=400,
                    detail={"error": {"code": "validation_error", "message": f"Brain prompt exceeds {p_max} characters"}},
                )
            est = estimate_tokens(body.brainPrompt)
            if est > budget and est <= BUDGET_MAX_TOKENS:
                budget = est
            saved = instruction_store.save_brain_prompt(body.sessionId, body.brainPrompt, budget_tokens=budget)
        elif body.agentBrief is not None:
            from server.brain.agent_script_compiler import compile_agent_from_brief

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            prev_compiled = prev_meta.get("brainPrompt") if prev_meta.get("compiledVersion") else None
            if body.callEndPolicy is None:
                policy = normalize_call_end_policy(prev_meta.get("callEndPolicy"), language=lang)
            try:
                compiled, script_result, raw_est, _compiled_est, effective_budget = await compile_agent_from_brief(
                    brief=body.agentBrief,
                    language=lang,
                    style=body.responseStyle,
                    budget_tokens=budget,
                    previous_compiled=prev_compiled,
                    call_end_policy=policy,
                )
            except (PromptSectionTooLong, PromptBudgetExceeded):
                raise
            except Exception as exc:
                from server.utils.logger import logger

                logger.error(f"[AGENT_SCRIPT] compile failed, deterministic fallback: {type(exc).__name__}: {str(exc)[:240]}")
                compiled, script_result, raw_est, _compiled_est, effective_budget = await compile_agent_from_brief(
                    brief=body.agentBrief,
                    language=lang,
                    style=body.responseStyle,
                    budget_tokens=budget,
                    previous_compiled=prev_compiled,
                    call_end_policy=policy,
                    use_llm=False,
                )
            budget = effective_budget
            from server.brain.agent_script_compiler import build_compiler_sections

            compiler_sections = build_compiler_sections(
                user_script=script_result.agent_script,
                platform_call_rules=script_result.platform_call_rules,
                compiled_brain=compiled,
                language=lang,
                style=body.responseStyle,
                call_end_policy=policy,
            )
            saved = instruction_store.save_agent_script(
                body.sessionId,
                body.agentBrief,
                script_result.agent_script,
                script_result.response_style or body.responseStyle,
                compiled_brain=compiled,
                optimizer_report=script_result.to_dict(),
                source_checksum=script_result.source_checksum,
                language=lang,
                budget_tokens=budget,
                raw_token_estimate=raw_est,
                call_end_policy=policy,
            )
        else:
            behaviour = body.behaviourInstructions if body.behaviourInstructions is not None else body.instructions or ""
            business = body.businessInstructions or ""
            from server.brain.session_brain_compiler import compile_session_brain

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            prev_compiled = prev_meta.get("brainPrompt") if prev_meta.get("compiledVersion") else None
            compiled, opt, raw_est, compiled_est = await compile_session_brain(
                behaviour=behaviour,
                business=business,
                language=lang,
                style=body.responseStyle,
                budget_tokens=budget,
                previous_compiled=prev_compiled,
                call_end_policy=policy,
            )
            saved = instruction_store.save_compiled(
                body.sessionId,
                behaviour,
                business,
                body.responseStyle,
                compiled_brain=compiled,
                optimizer_report=opt.to_dict(),
                source_checksum=opt.source_checksum,
                language=lang,
                budget_tokens=budget,
                raw_token_estimate=raw_est,
                call_end_policy=policy,
            )
    except PromptSectionTooLong as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "prompt_section_too_long",
                    "message": str(e),
                    "section": e.section,
                    "words": e.words,
                    "wordLimit": e.word_limit,
                    "chars": e.chars,
                    "charLimit": e.char_limit,
                }
            },
        ) from e
    except PromptBudgetExceeded as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "prompt_budget_exceeded",
                    "message": str(e),
                    "estimatedTokens": e.estimated,
                    "budgetTokens": e.budget,
                    "overBy": e.over_by,
                }
            },
        ) from e

    try:
        if get_settings().use_versioned_brains:
            from server.brain.instruction_bridge import sync_legacy_instructions_to_business_brain

            await sync_legacy_instructions_to_business_brain(
                behaviour=saved.get("behaviour", ""),
                business=saved.get("business", ""),
            )
    except Exception:
        pass

    persisted = await instruction_store.persist_to_db(body.sessionId)

    payload = {
        "ok": True,
        "sessionId": body.sessionId,
        "brainPrompt": saved["brainPrompt"][:800] + ("..." if len(saved["brainPrompt"]) > 800 else ""),
        "brainPromptFull": saved["brainPrompt"],
        "compiledBrainPrompt": saved["brainPrompt"],
        "estimatedTokens": saved["estimatedTokens"],
        "budgetTokens": saved["budgetTokens"],
        "headroom": saved["budgetTokens"] - saved["estimatedTokens"],
        "cacheEligible": cache_eligible(saved["estimatedTokens"]),
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "customBrainPrompt": saved.get("customBrainPrompt", False),
        "behaviour": saved.get("behaviour", ""),
        "business": saved.get("business", ""),
        "agentBrief": saved.get("agentBrief", ""),
        "agentScript": saved.get("agentScript", ""),
        "responseStyle": saved.get("style"),
        "behaviourLength": len(saved.get("behaviour") or ""),
        "businessLength": len(saved.get("business") or ""),
        "updatedAt": saved["updatedAt"],
        "compiledVersion": saved.get("compiledVersion", 0),
        "optimizerReport": saved.get("optimizerReport"),
        "rawTokenEstimate": saved.get("rawTokenEstimate", 0),
        "tokensSaved": max(0, int(saved.get("rawTokenEstimate") or 0) - int(saved.get("estimatedTokens") or 0)),
        "callEndPolicy": saved.get("callEndPolicy"),
        "language": saved.get("language"),
        "persistedToDb": persisted,
    }
    if compiler_sections is not None:
        payload["compilerSections"] = compiler_sections
    from server.brain.script_entities import entity_tags_to_api, parse_entity_tags

    from server.brain.script_entities import strip_entity_tags_section

    saved_script = str(saved.get("agentScript") or "")
    payload["scriptEntities"] = entity_tags_to_api(parse_entity_tags(saved_script))
    payload["agentScriptBody"] = strip_entity_tags_section(saved_script)
    return payload


@router.get("/api/instructions")
async def get_instructions(
    sessionId: str = "default",
    includeCompiled: bool = Query(False),
    includeCompilerSections: bool = Query(False),
):
    from server.call.call_end_policy import normalize_call_end_policy

    meta = instruction_store.get_with_meta(sessionId)
    b_max, z_max, p_max = _limits()
    budget = resolve_brain_budget(sessionId)
    est = int(meta.get("estimatedTokens") or estimate_tokens(meta.get("brainPrompt") or ""))
    if not meta.get("present"):
        default = get_factory_brain_prompt()
        meta["brainPrompt"] = default
        est = estimate_tokens(default)
    payload = {
        "sessionId": sessionId,
        **meta,
        "callEndPolicy": normalize_call_end_policy(
            meta.get("callEndPolicy"),
            language=meta.get("language") or "te-IN",
        ),
        "budgetTokens": budget,
        "headroom": max(0, budget - est),
        "cacheEligible": cache_eligible(est),
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "budgetMinTokens": BUDGET_MIN_TOKENS,
        "budgetMaxTokens": BUDGET_MAX_TOKENS,
        "maxWords": MAX_BRAIN_PROMPT_WORDS,
        "recommendedBehaviourWords": RECOMMENDED_BEHAVIOUR_WORDS,
        "recommendedBusinessWords": RECOMMENDED_BUSINESS_WORDS,
        "recommendedAgentBriefWords": RECOMMENDED_AGENT_BRIEF_WORDS,
        "recommendedAgentScriptWords": RECOMMENDED_AGENT_SCRIPT_WORDS,
        "memoryHeadroomTokens": MEMORY_HEADROOM_TOKENS,
        "limits": {
            "brainPromptMax": p_max,
            "behaviourMax": b_max,
            "businessMax": z_max,
            "agentBriefMax": MAX_AGENT_BRIEF_CHARS,
            "agentScriptMax": MAX_AGENT_SCRIPT_CHARS,
            "behaviourMaxWords": MAX_BEHAVIOUR_WORDS,
            "businessMaxWords": MAX_BUSINESS_WORDS,
            "agentBriefMaxWords": MAX_AGENT_BRIEF_WORDS,
            "agentScriptMaxWords": MAX_AGENT_SCRIPT_WORDS,
            "recommendedBehaviourWords": RECOMMENDED_BEHAVIOUR_WORDS,
            "recommendedBusinessWords": RECOMMENDED_BUSINESS_WORDS,
            "recommendedAgentBriefWords": RECOMMENDED_AGENT_BRIEF_WORDS,
            "recommendedAgentScriptWords": RECOMMENDED_AGENT_SCRIPT_WORDS,
            "maxWords": MAX_BRAIN_PROMPT_WORDS,
            "cacheMinTokens": CACHE_MIN_TOKENS,
            "memoryHeadroomTokens": MEMORY_HEADROOM_TOKENS,
        },
    }
    if not includeCompiled:
        payload.pop("brainPrompt", None)
    if includeCompilerSections and meta.get("present"):
        from server.brain.agent_script_compiler import build_compiler_sections

        opt = meta.get("optimizerReport") if isinstance(meta.get("optimizerReport"), dict) else {}
        brain = meta.get("brainPrompt") or ""
        payload["compilerSections"] = build_compiler_sections(
            user_script=str(meta.get("agentScript") or ""),
            platform_call_rules=str(opt.get("platform_call_rules") or ""),
            compiled_brain=brain,
            language=meta.get("language") or "te-IN",
            style=meta.get("style"),
            call_end_policy=payload.get("callEndPolicy"),
        )
    if meta.get("present"):
        from server.brain.script_entities import entity_tags_to_api, parse_entity_tags

        from server.brain.script_entities import entities_have_values

        parsed = parse_entity_tags(str(meta.get("agentScript") or ""))
        if not entities_have_values(parsed):
            parsed = parse_entity_tags(str(meta.get("brainPrompt") or ""))
        payload["scriptEntities"] = entity_tags_to_api(parsed)
        from server.brain.script_entities import script_conflicts_with_brief, strip_entity_tags_section

        brief_text = str(meta.get("agentBrief") or "")
        script_text = str(meta.get("agentScript") or "")
        payload["scriptConflictWithBrief"] = bool(
            brief_text.strip()
            and script_text.strip()
            and script_conflicts_with_brief(script_text, brief_text, language=meta.get("language") or "te-IN")
        )
        payload["agentScriptBody"] = strip_entity_tags_section(script_text)
    return payload


@router.get("/api/instructions/live-prompt-preview")
async def instructions_live_prompt_preview(
    sessionId: str = "default",
    direction: str = Query("outbound"),
    pipeline: str = Query("realtime_voice"),
    llmModel: str | None = Query(None),
):
    from server.call.call_prompt_preview import get_session_live_prompt_preview
    from server.realtime.models import is_gemini_live_voice_model

    meta = instruction_store.get_with_meta(sessionId)
    lang = meta.get("language") or "te-IN"
    model = (llmModel or "").strip()
    if not model:
        from server.services.runtime_settings import runtime_settings

        rt = runtime_settings.get(sessionId)
        model = str(rt.get("openaiModel") or rt.get("llmModel") or "").strip()
    provider = "gemini" if is_gemini_live_voice_model(model) else "openai"
    if not model:
        model = "gemini-3.8-live" if provider == "gemini" else "gpt-realtime-2.1-mini"
    stack_override = {
        "pipeline": pipeline,
        "language": lang,
        "llm": {"provider": provider, "model": model},
    }
    try:
        return await get_session_live_prompt_preview(
            session_id=sessionId,
            direction=direction,
            pipeline=pipeline,
            llm_model=model,
            stack_override=stack_override,
            language=lang,
        )
    except Exception as exc:
        from server.services.pstn_stack import PstnStackValidationError
        from server.utils.errors import AppError

        if isinstance(exc, AppError):
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        if isinstance(exc, PstnStackValidationError):
            raise HTTPException(
                status_code=422,
                detail={"message": str(exc), "issues": list(exc.details or [])},
            ) from exc
        raise


@router.delete("/api/instructions")
async def clear_instructions(sessionId: str = "default"):
    instruction_store.clear(sessionId)
    session_memory.clear(sessionId)
    try:
        from server.services.saved_instruction_store import delete as delete_saved

        await delete_saved(sessionId)
    except Exception:
        pass
    return {"ok": True, "sessionId": sessionId, "cleared": True}
