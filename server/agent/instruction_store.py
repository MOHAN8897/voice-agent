"""
Instruction store — per-session behaviour/business + composed brainPrompt.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from server.agent.brain_prompt_composer import (
    compose_brain_prompt,
    estimate_tokens,
    sanitize_agent_brief,
    sanitize_agent_script,
    sanitize_behaviour,
    sanitize_brain_prompt,
    sanitize_business,
    validate_brain_prompt_budget,
)
from server.prompts.brain_prompt import get_factory_brain_prompt
from server.call.call_end_policy import normalize_call_end_policy
from server.prompts.agent_voice_rules import call_end_policy_section
from server.prompts.voice_defaults import (
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
    DEFAULT_RESPONSE_STYLE,
    default_style_for,
    style_for_language,
)
from server.services.session_persist import session_persist

_TTL_SECONDS = 60 * 60 * 24


def _is_saved_entry(entry: dict) -> bool:
    return bool(
        str(entry.get("agentScript") or "").strip()
        or str(entry.get("agentBrief") or "").strip()
        or str(entry.get("brainPrompt") or "").strip()
        or str(entry.get("behaviour") or "").strip()
        or str(entry.get("business") or "").strip()
    )


def _resolve_policy(raw, language: str | None) -> dict:
    return normalize_call_end_policy(raw, language=language)


def _ensure_hangup_section(brain: str, *, language: str, policy: dict | None) -> str:
    text = (brain or "").strip()
    if "--- CALL END POLICY ---" in text:
        return text
    return f"{text}\n\n{call_end_policy_section(language, policy)}".strip()


class InstructionStore:
    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._hydrate_from_disk()

    def _hydrate_from_disk(self) -> None:
        with self._lock:
            for sid, entry in session_persist.all_instructions().items():
                if entry.get("updatedAt"):
                    self._store[sid] = dict(entry)

    def _persist(self, session_id: str) -> None:
        entry = self._store.get(session_id)
        if entry:
            session_persist.set_instructions(session_id, entry)

    def _entry(self, session_id: str) -> Optional[dict]:
        entry = self._store.get(session_id)
        if not entry:
            return None
        if _is_saved_entry(entry):
            return entry
        if time.time() - float(entry.get("updatedAt") or 0) > _TTL_SECONDS:
            self._store.pop(session_id, None)
            return None
        return entry

    def save(
        self,
        session_id: str,
        behaviour: str = "",
        business: str = "",
        style: str | None = None,
        *,
        language: str = "te-IN",
        budget_tokens: int = 2500,
    ) -> dict:
        """Legacy synchronous compose — prefer save_compiled from routes after optimizer."""
        b = sanitize_behaviour(behaviour or "")
        z = sanitize_business(business or "")
        with self._lock:
            prev = self._store.get(session_id, {})
            style_val = style_for_language(style or prev.get("style"), language)
            brain_prompt = compose_brain_prompt(
                behaviour=b or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                business=z or DEFAULT_BUSINESS_INSTRUCTIONS,
                language=language,
                style=style_val,
            )
            estimated = validate_brain_prompt_budget(brain_prompt, budget_tokens)
            self._store[session_id] = {
                "text": b,
                "behaviour": b,
                "business": z,
                "style": style_val,
                "brainPrompt": brain_prompt,
                "customBrainPrompt": False,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": time.time(),
                "compiledVersion": int(prev.get("compiledVersion", 0)),
                "optimizerReport": prev.get("optimizerReport"),
                "sourceChecksum": prev.get("sourceChecksum"),
                "rawTokenEstimate": prev.get("rawTokenEstimate"),
                "callEndPolicy": _resolve_policy(prev.get("callEndPolicy"), language),
                "language": prev.get("language") or language,
            }
            self._persist(session_id)
            return self._pack_entry(self._store[session_id])

    def save_agent_script(
        self,
        session_id: str,
        agent_brief: str,
        agent_script: str,
        style: str | None,
        *,
        compiled_brain: str,
        optimizer_report: dict,
        source_checksum: str,
        language: str = "te-IN",
        budget_tokens: int = 2500,
        raw_token_estimate: int = 0,
        call_end_policy: dict | None = None,
    ) -> dict:
        """Save short agent brief + GPT-expanded calling script as cached brain."""
        brief = sanitize_agent_brief(agent_brief or "")
        script = sanitize_agent_script(agent_script or "")
        with self._lock:
            prev = self._store.get(session_id, {})
            style_val = style_for_language(style or prev.get("style"), language)
            estimated = validate_brain_prompt_budget(compiled_brain, budget_tokens)
            version = int(prev.get("compiledVersion", 0)) + 1
            policy = _resolve_policy(
                call_end_policy if call_end_policy is not None else prev.get("callEndPolicy"),
                language,
            )
            self._store[session_id] = {
                "text": "",
                "behaviour": "",
                "business": "",
                "agentBrief": brief,
                "agentScript": script,
                "style": style_val,
                "brainPrompt": compiled_brain,
                "customBrainPrompt": False,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": time.time(),
                "compiledVersion": version,
                "optimizerReport": optimizer_report,
                "sourceChecksum": source_checksum,
                "rawTokenEstimate": raw_token_estimate,
                "language": language,
                "callEndPolicy": policy,
            }
            self._persist(session_id)
            return self._pack_entry(self._store[session_id])

    def save_compiled(
        self,
        session_id: str,
        behaviour: str,
        business: str,
        style: str | None,
        *,
        compiled_brain: str,
        optimizer_report: dict,
        source_checksum: str,
        language: str = "te-IN",
        budget_tokens: int = 2500,
        raw_token_estimate: int = 0,
        call_end_policy: dict | None = None,
    ) -> dict:
        """Save raw channels + LLM/deterministic compiled brain for cache breakpoint."""
        b = sanitize_behaviour(behaviour or "")
        z = sanitize_business(business or "")
        with self._lock:
            prev = self._store.get(session_id, {})
            style_val = style_for_language(style or prev.get("style"), language)
            estimated = validate_brain_prompt_budget(compiled_brain, budget_tokens)
            version = int(prev.get("compiledVersion", 0)) + 1
            self._store[session_id] = {
                "text": b,
                "behaviour": b,
                "business": z,
                "style": style_val,
                "brainPrompt": compiled_brain,
                "customBrainPrompt": False,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": time.time(),
                "compiledVersion": version,
                "optimizerReport": optimizer_report,
                "sourceChecksum": source_checksum,
                "rawTokenEstimate": raw_token_estimate,
                "language": language,
                "callEndPolicy": _resolve_policy(
                    call_end_policy if call_end_policy is not None else prev.get("callEndPolicy"),
                    language,
                ),
            }
            self._persist(session_id)
            return self._pack_entry(self._store[session_id])

    def _legacy_brief(self, e: dict) -> str:
        if e.get("agentBrief"):
            return e["agentBrief"]
        b = (e.get("behaviour") or "").strip()
        z = (e.get("business") or "").strip()
        if b and z:
            return f"{b}\n\n{z}"
        return b or z

    def _pack_entry(self, e: dict) -> dict:
        return {
            "text": e.get("behaviour", ""),
            "behaviour": e.get("behaviour", ""),
            "business": e.get("business", ""),
            "agentBrief": e.get("agentBrief", ""),
            "agentScript": e.get("agentScript", ""),
            "style": e.get("style", DEFAULT_RESPONSE_STYLE),
            "brainPrompt": e.get("brainPrompt", ""),
            "customBrainPrompt": e.get("customBrainPrompt", False),
            "estimatedTokens": e.get("estimatedTokens", 0),
            "budgetTokens": e.get("budgetTokens", 2500),
            "updatedAt": e.get("updatedAt"),
            "compiledVersion": e.get("compiledVersion", 0),
            "optimizerReport": e.get("optimizerReport"),
            "sourceChecksum": e.get("sourceChecksum"),
            "rawTokenEstimate": e.get("rawTokenEstimate", 0),
            "language": e.get("language") or "te-IN",
            "callEndPolicy": _resolve_policy(e.get("callEndPolicy"), e.get("language") or "te-IN"),
        }

    def patch_call_end_policy(
        self,
        session_id: str,
        policy: dict,
        *,
        language: str | None = None,
        compiled_brain: str | None = None,
        estimated_tokens: int | None = None,
        budget_tokens: int | None = None,
    ) -> dict:
        """Persist call-end policy; optionally swap the compiled brain after a reassemble."""
        with self._lock:
            prev = self._store.get(session_id) or {
                "behaviour": "",
                "business": "",
                "text": "",
                "style": DEFAULT_RESPONSE_STYLE,
                "brainPrompt": "",
                "updatedAt": time.time(),
            }
            prev["callEndPolicy"] = _resolve_policy(policy, language or prev.get("language"))
            if language:
                prev["language"] = language
            if compiled_brain:
                prev["brainPrompt"] = compiled_brain
                prev["customBrainPrompt"] = False
            if estimated_tokens is not None:
                prev["estimatedTokens"] = estimated_tokens
            if budget_tokens is not None:
                prev["budgetTokens"] = budget_tokens
            prev["updatedAt"] = time.time()
            self._store[session_id] = prev
            self._persist(session_id)
            return self._pack_entry(prev)

    def get_call_end_policy(self, session_id: str) -> dict | None:
        with self._lock:
            e = self._entry(session_id)
            if not e:
                return None
            policy = e.get("callEndPolicy")
            return _resolve_policy(policy, e.get("language") or "te-IN")

    def get_language(self, session_id: str) -> str:
        with self._lock:
            e = self._entry(session_id)
            if e and e.get("language"):
                return str(e["language"])
            return "te-IN"

    def save_brain_prompt(
        self,
        session_id: str,
        brain_prompt: str,
        *,
        budget_tokens: int = 2500,
    ) -> dict:
        """Save a single user-edited brain prompt document."""
        text = sanitize_brain_prompt(brain_prompt)
        if not text:
            text = get_factory_brain_prompt()
        with self._lock:
            prev = self._store.get(session_id, {})
            language = prev.get("language") or "te-IN"
            policy = _resolve_policy(prev.get("callEndPolicy"), language)
            text = _ensure_hangup_section(text, language=language, policy=policy)
            estimated = validate_brain_prompt_budget(text, budget_tokens)
            self._store[session_id] = {
                "text": "",
                "behaviour": "",
                "business": "",
                "style": prev.get("style") or DEFAULT_RESPONSE_STYLE,
                "brainPrompt": text,
                "customBrainPrompt": True,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": time.time(),
                "language": language,
                "callEndPolicy": policy,
                "agentBrief": prev.get("agentBrief", ""),
                "agentScript": prev.get("agentScript", ""),
            }
            e = self._store[session_id]
            self._persist(session_id)
            return self._pack_entry(e)

    def get_brain_prompt(
        self,
        session_id: str,
        *,
        language: str = "te-IN",
        budget_tokens: int = 2500,
    ) -> str:
        with self._lock:
            e = self._entry(session_id)
            if e and e.get("brainPrompt"):
                return e["brainPrompt"]
        try:
            from server.config.env import get_settings

            if get_settings().use_versioned_brains:
                from server.brain.compiled_brain_service import get_cached_compiled_brain

                snap = get_cached_compiled_brain()
                if snap:
                    return snap["compiled_text"]
        except Exception:
            pass
        return compose_brain_prompt(
            behaviour=self.get_behaviour(session_id),
            business=self.get_business(session_id),
            language=language,
            style=self.get_style(session_id),
        )

    def get_behaviour(self, session_id: str) -> str:
        with self._lock:
            e = self._entry(session_id)
            if e and e["behaviour"]:
                return e["behaviour"]
            return DEFAULT_BEHAVIOUR_INSTRUCTIONS

    def get_business(self, session_id: str) -> str:
        with self._lock:
            e = self._entry(session_id)
            if e and e["business"]:
                return e["business"]
            return DEFAULT_BUSINESS_INSTRUCTIONS

    def get_style(self, session_id: str) -> str | None:
        with self._lock:
            e = self._entry(session_id)
            if e and e.get("style"):
                return style_for_language(e["style"], e.get("language"))
            return default_style_for(e.get("language") if e else None)

    def get(self, session_id: str) -> str:
        return self.get_behaviour(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
        session_persist.delete_instructions(session_id)
        try:
            from server.services.saved_instruction_store import queue_delete

            queue_delete(session_id)
        except Exception:
            pass

    async def hydrate_from_db(self) -> int:
        """Overlay Postgres-saved scripts after disk hydrate (DB wins)."""
        try:
            from server.services.saved_instruction_store import load_all, upsert

            rows = await load_all()
        except Exception:
            return 0
        with self._lock:
            snapshot = {sid: dict(entry) for sid, entry in self._store.items()}
            for sid, payload in rows.items():
                if not isinstance(payload, dict) or not payload.get("updatedAt"):
                    continue
                self._store[sid] = dict(payload)
                session_persist.set_instructions(sid, payload)
        for sid, entry in snapshot.items():
            if sid in rows or not _is_saved_entry(entry):
                continue
            try:
                await upsert(sid, entry)
            except Exception:
                pass
        return len(rows)

    def raw_entry(self, session_id: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(session_id)
            return dict(entry) if entry else None

    async def persist_to_db(self, session_id: str) -> bool:
        entry = self.raw_entry(session_id)
        if not entry:
            return False
        try:
            from server.services.saved_instruction_store import upsert

            return await upsert(session_id, entry)
        except Exception as exc:
            from server.utils.logger import logger

            logger.warning("[INSTRUCTIONS] Postgres persist failed for %s: %s", session_id, exc)
            return False

    def get_with_meta(self, session_id: str) -> dict:
        with self._lock:
            e = self._entry(session_id)
            if not e:
                brain = get_factory_brain_prompt()
                return {
                    "text": DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                    "behaviour": DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                    "business": DEFAULT_BUSINESS_INSTRUCTIONS,
                    "agentBrief": "",
                    "agentScript": "",
                    "brainPrompt": brain,
                    "customBrainPrompt": False,
                    "estimatedTokens": estimate_tokens(brain),
                    "updatedAt": None,
                    "present": False,
                    "style": DEFAULT_RESPONSE_STYLE,
                    "usingDefaults": True,
                    "callEndPolicy": _resolve_policy(None, "te-IN"),
                    "language": "te-IN",
                }
            using_custom = bool(e.get("customBrainPrompt"))
            has_agent_brief = bool(e.get("agentBrief"))
            has_agent_script = bool(str(e.get("agentScript") or "").strip())
            has_legacy = bool(e.get("behaviour") or e.get("business"))
            return {
                "text": e["behaviour"] or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                "behaviour": e["behaviour"] or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                "business": e["business"] or DEFAULT_BUSINESS_INSTRUCTIONS,
                "agentBrief": self._legacy_brief(e) if not has_agent_brief else e.get("agentBrief", ""),
                "agentScript": e.get("agentScript", ""),
                "brainPrompt": e.get("brainPrompt") or compose_brain_prompt(
                    behaviour=e.get("behaviour", ""),
                    business=e.get("business", ""),
                    language=e.get("language") or "te-IN",
                    style=e.get("style"),
                ),
                "customBrainPrompt": using_custom,
                "estimatedTokens": e.get("estimatedTokens") or estimate_tokens(e.get("brainPrompt", "")),
                "budgetTokens": e.get("budgetTokens"),
                "updatedAt": e["updatedAt"],
                "present": using_custom or has_agent_brief or has_agent_script or has_legacy,
                "style": style_for_language(e.get("style"), e.get("language")),
                "usingDefaults": not using_custom and not has_agent_brief and not has_agent_script and not has_legacy,
                "compiledVersion": e.get("compiledVersion", 0),
                "optimizerReport": e.get("optimizerReport"),
                "sourceChecksum": e.get("sourceChecksum"),
                "rawTokenEstimate": e.get("rawTokenEstimate", 0),
                "callEndPolicy": _resolve_policy(e.get("callEndPolicy"), e.get("language") or "te-IN"),
                "language": e.get("language") or "te-IN",
            }

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store)}


instruction_store = InstructionStore()
