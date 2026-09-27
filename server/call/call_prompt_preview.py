"""Build the live prompt actually sent to the model for a call."""
from __future__ import annotations

from typing import Any

from server.agent.brain_prompt_composer import estimate_tokens
from server.call.call_brain_lock import BrainSource, classify_brain_source
from server.call.call_context import get as get_call_ctx
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.realtime.models import realtime_voice_llm_provider
from server.services.pstn_text_chunker import extract_opening_greeting
from server.utils.errors import AppError, ErrorCode


def _opening_from_brain(brain: str | None, *, language: str, direction: str | None) -> str:
    if not (brain or "").strip():
        return ""
    try:
        return (extract_opening_greeting(brain, language, direction=direction) or "").strip()
    except Exception:
        return ""


def build_live_prompt_for_call(
    compiled_brain: str | None,
    *,
    pipeline: str,
    stack_override: dict[str, Any] | None,
    llm_model: str | None,
    language: str,
    direction: str | None,
    caller_id: str | None,
    opening_greeting: str | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Return (live_prompt, provider_id, layers metadata)."""
    brain = (compiled_brain or "").strip()
    opening = (opening_greeting or "").strip() or _opening_from_brain(
        brain, language=language, direction=direction
    )
    layers: list[dict[str, Any]] = [
        {
            "layer": "compiled_brain",
            "precedence": 1,
            "description": "Locked compiled brain (user script + platform assembly)",
            "char_count": len(brain),
            "token_estimate": estimate_tokens(brain) if brain else 0,
        },
    ]

    pipe = (pipeline or "realtime_text").strip().lower()
    if pipe == "realtime_voice":
        from server.realtime.voice_instructions import build_realtime_voice_instructions

        live = build_realtime_voice_instructions(
            brain or None,
            model=llm_model,
            stack_override=stack_override,
            caller_id=caller_id,
            language=language,
            direction=direction,
            opening_greeting=opening or None,
        )
        provider, _ = realtime_voice_llm_provider(stack_override, llm_model)
        layers.append(
            {
                "layer": "realtime_voice_session",
                "precedence": 2,
                "description": (
                    "Provider live rules (language lock, first-turn, call direction, tools) "
                    f"via {provider}"
                ),
                "char_count": max(0, len(live) - len(brain)),
                "token_estimate": estimate_tokens(live) - estimate_tokens(brain) if live else 0,
            }
        )
        return live, provider, layers

    from server.realtime.text_session import build_session_instructions

    live = build_session_instructions(
        brain or None,
        caller_id=caller_id,
        language=language,
    )
    layers.append(
        {
            "layer": "realtime_text_session",
            "precedence": 2,
            "description": "Realtime text session rules appended to compiled brain",
            "char_count": max(0, len(live) - len(brain)),
            "token_estimate": estimate_tokens(live) - estimate_tokens(brain) if live else 0,
        }
    )
    return live, "openai", layers


async def get_call_prompt_preview(
    call_id: str,
    *,
    redacted: bool = False,
) -> dict[str, Any]:
    ctx = get_call_ctx(call_id)
    stored = await call_store.get(call_id)
    if not ctx and not stored:
        raise AppError(ErrorCode.NOT_FOUND, message="Call not found", status_code=404)

    meta = call_ledger.read_meta(call_id) if call_ledger.meta_path(call_id).exists() else {}

    agent_id = (ctx.agent_id if ctx else None) or stored.get("agent_id") or meta.get("agent_id")
    session_id = (ctx.session_id if ctx else None) or stored.get("session_id") or meta.get("session_id")
    config_session_id = meta.get("config_session_id") or session_id
    direction = (ctx.direction if ctx else None) or stored.get("direction") or meta.get("direction")
    channel = (ctx.channel if ctx else None) or stored.get("channel") or meta.get("channel")
    language = meta.get("language") or "te-IN"
    pipeline = (ctx.pipeline if ctx else None) or stored.get("pipeline") or meta.get("pipeline") or "realtime_text"
    caller_id = meta.get("caller_id")

    compiled_version = (
        (ctx.compiled_brain_version if ctx else None)
        or stored.get("compiled_brain_version")
        or meta.get("compiled_brain_version")
    )
    brain_source: BrainSource = meta.get("brain_source") or classify_brain_source(
        str(compiled_version or "")
    )

    compiled_text = ""
    if ctx and (ctx.compiled_brain_text or "").strip():
        compiled_text = ctx.compiled_brain_text.strip()
    elif (meta.get("compiled_brain_text") or "").strip():
        compiled_text = str(meta["compiled_brain_text"]).strip()
    elif agent_id:
        from server.call.call_brain_lock import resolve_locked_compiled_brain

        _ver, text, src = await resolve_locked_compiled_brain(
            str(agent_id),
            session_id=str(config_session_id or session_id or "") or None,
        )
        if text:
            compiled_text = text
            if not compiled_version:
                compiled_version = _ver
            brain_source = src

    stack_override: dict[str, Any] | None = None
    llm_model: str | None = None
    if ctx:
        stack_override = ctx.resolved_stack.to_safe_dict()
        llm_model = ctx.resolved_stack.llm.model
    elif meta.get("resolved_stack"):
        stack_override = meta["resolved_stack"]
        llm = (stack_override or {}).get("llm") or {}
        llm_model = llm.get("model") if isinstance(llm, dict) else None

    from server.brain.script_entities import entity_tags_to_api, parse_entity_tags

    from server.brain.script_entities import entity_tags_to_api, parse_entity_tags

    opening = _opening_from_brain(compiled_text, language=language, direction=direction)
    live_prompt, provider, layers = build_live_prompt_for_call(
        compiled_text,
        pipeline=pipeline,
        stack_override=stack_override,
        llm_model=llm_model,
        language=language,
        direction=direction,
        caller_id=str(caller_id) if caller_id else None,
        opening_greeting=opening or None,
    )

    preview_text = live_prompt
    if redacted and compiled_text:
        from server.brain.compiled_brain_service import compiled_brain_service

        preview_text = live_prompt.replace(
            compiled_text,
            compiled_brain_service.redacted_preview(compiled_text),
            1,
        )

    return {
        "call_id": call_id,
        "agent_id": agent_id,
        "session_id": session_id,
        "config_session_id": config_session_id if config_session_id != session_id else None,
        "channel": channel,
        "direction": direction,
        "language": language,
        "pipeline": pipeline,
        "provider": provider,
        "brain_source": brain_source,
        "compiled_brain_version": compiled_version,
        "opening_line": opening,
        "script_entities": entity_tags_to_api(parse_entity_tags(compiled_text)),
        "layers": layers,
        "compiled_brain_chars": len(compiled_text),
        "live_prompt_chars": len(live_prompt),
        "token_estimate": estimate_tokens(live_prompt),
        "live_prompt": preview_text,
        "note": (
            "This is the instruction bundle used at connect time: locked compiled brain "
            "plus live session rules. Test Studio session brain overrides published agent "
            "when present at call start."
        ),
    }


async def get_session_live_prompt_preview(
    *,
    session_id: str,
    direction: str | None = "outbound",
    pipeline: str = "realtime_voice",
    llm_model: str | None = None,
    stack_override: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Preview live LLM instructions for a Test Studio session (no active call required)."""
    from server.agent.instruction_store import instruction_store
    from server.brain.script_entities import entity_tags_to_api, parse_entity_tags
    from server.services.pstn_text_chunker import extract_prewarm_greeting

    meta = instruction_store.get_with_meta(session_id)
    compiled_text = (meta.get("brainPrompt") or "").strip()
    if not compiled_text:
        raise AppError(
            ErrorCode.NOT_FOUND,
            message="No compiled brain for this session — create agent script first",
            status_code=404,
        )
    lang = language or meta.get("language") or "te-IN"
    dir_norm = (
        "inbound"
        if str(direction or "").strip().lower() in ("inbound", "incoming")
        else "outbound"
    )
    pipe = (pipeline or "realtime_voice").strip().lower()
    opening = _opening_from_brain(compiled_text, language=lang, direction=dir_norm)
    prewarm = extract_prewarm_greeting(compiled_text, lang, direction=dir_norm)
    live_prompt, provider, layers = build_live_prompt_for_call(
        compiled_text,
        pipeline=pipe,
        stack_override=stack_override,
        llm_model=llm_model,
        language=lang,
        direction=dir_norm,
        caller_id=None if dir_norm == "outbound" else "preview",
        opening_greeting=opening or None,
    )
    entities = entity_tags_to_api(parse_entity_tags(compiled_text))
    return {
        "session_id": session_id,
        "direction": dir_norm,
        "language": lang,
        "pipeline": pipe,
        "provider": provider,
        "compiled_brain_version": meta.get("compiledVersion"),
        "brain_source": classify_brain_source(str(meta.get("compiledVersion") or "")),
        "script_entities": entities,
        "opening_line": opening,
        "prewarm_greeting_line": prewarm,
        "layers": layers,
        "compiled_brain": compiled_text,
        "compiled_brain_chars": len(compiled_text),
        "live_prompt": live_prompt,
        "live_prompt_chars": len(live_prompt),
        "token_estimate": estimate_tokens(live_prompt),
        "note": (
            "live_prompt is the system instruction bundle at PSTN connect "
            "(compiled brain + Gemini/OpenAI live rules). prewarm_greeting_line is the "
            "deferred opening PCM text at dial time."
        ),
    }
