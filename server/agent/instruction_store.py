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
    sanitize_behaviour,
    sanitize_brain_prompt,
    sanitize_business,
    validate_brain_prompt_budget,
)
from server.prompts.brain_prompt import get_factory_brain_prompt
from server.prompts.voice_defaults import (
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
    DEFAULT_RESPONSE_STYLE,
)
from server.services.session_persist import session_persist

_TTL_SECONDS = 60 * 60 * 24


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
        if entry and time.time() - entry["updatedAt"] > _TTL_SECONDS:
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
            style_val = (style or prev.get("style") or DEFAULT_RESPONSE_STYLE)[:100]
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
    ) -> dict:
        """Save short agent brief + GPT-expanded calling script as cached brain."""
        brief = sanitize_agent_brief(agent_brief or "")
        script = (agent_script or "").strip()
        with self._lock:
            prev = self._store.get(session_id, {})
            style_val = (style or prev.get("style") or DEFAULT_RESPONSE_STYLE)[:100]
            estimated = validate_brain_prompt_budget(compiled_brain, budget_tokens)
            version = int(prev.get("compiledVersion", 0)) + 1
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
    ) -> dict:
        """Save raw channels + LLM/deterministic compiled brain for cache breakpoint."""
        b = sanitize_behaviour(behaviour or "")
        z = sanitize_business(business or "")
        with self._lock:
            prev = self._store.get(session_id, {})
            style_val = (style or prev.get("style") or DEFAULT_RESPONSE_STYLE)[:100]
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
        }

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
        estimated = validate_brain_prompt_budget(text, budget_tokens)
        with self._lock:
            self._store[session_id] = {
                "text": "",
                "behaviour": "",
                "business": "",
                "style": DEFAULT_RESPONSE_STYLE,
                "brainPrompt": text,
                "customBrainPrompt": True,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": time.time(),
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
                return e["style"]
            return DEFAULT_RESPONSE_STYLE

    def get(self, session_id: str) -> str:
        return self.get_behaviour(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
        session_persist.delete_instructions(session_id)

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
                }
            using_custom = bool(e.get("customBrainPrompt"))
            has_agent_brief = bool(e.get("agentBrief"))
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
                    style=e.get("style"),
                ),
                "customBrainPrompt": using_custom,
                "estimatedTokens": e.get("estimatedTokens") or estimate_tokens(e.get("brainPrompt", "")),
                "budgetTokens": e.get("budgetTokens"),
                "updatedAt": e["updatedAt"],
                "present": using_custom or has_agent_brief or has_legacy,
                "style": e.get("style") or DEFAULT_RESPONSE_STYLE,
                "usingDefaults": not using_custom and not has_agent_brief and not has_legacy,
                "compiledVersion": e.get("compiledVersion", 0),
                "optimizerReport": e.get("optimizerReport"),
                "sourceChecksum": e.get("sourceChecksum"),
                "rawTokenEstimate": e.get("rawTokenEstimate", 0),
            }

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store)}


instruction_store = InstructionStore()
