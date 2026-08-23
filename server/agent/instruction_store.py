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

_TTL_SECONDS = 60 * 60 * 24


class InstructionStore:
    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()

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
        budget_tokens: int = 1500,
    ) -> dict:
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
            }
            e = self._store[session_id]
            return {
                "text": b,
                "behaviour": b,
                "business": z,
                "style": style_val,
                "brainPrompt": brain_prompt,
                "customBrainPrompt": False,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": e["updatedAt"],
            }

    def save_brain_prompt(
        self,
        session_id: str,
        brain_prompt: str,
        *,
        budget_tokens: int = 1500,
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
            return {
                "text": "",
                "behaviour": "",
                "business": "",
                "style": DEFAULT_RESPONSE_STYLE,
                "brainPrompt": text,
                "customBrainPrompt": True,
                "estimatedTokens": estimated,
                "budgetTokens": budget_tokens,
                "updatedAt": e["updatedAt"],
            }

    def get_brain_prompt(
        self,
        session_id: str,
        *,
        language: str = "te-IN",
        budget_tokens: int = 1500,
    ) -> str:
        with self._lock:
            e = self._entry(session_id)
            if e and e.get("brainPrompt"):
                return e["brainPrompt"]
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

    def get_with_meta(self, session_id: str) -> dict:
        with self._lock:
            e = self._entry(session_id)
            if not e:
                brain = get_factory_brain_prompt()
                return {
                    "text": DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                    "behaviour": DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                    "business": DEFAULT_BUSINESS_INSTRUCTIONS,
                    "brainPrompt": brain,
                    "customBrainPrompt": False,
                    "estimatedTokens": estimate_tokens(brain),
                    "updatedAt": None,
                    "present": False,
                    "style": DEFAULT_RESPONSE_STYLE,
                    "usingDefaults": True,
                }
            using_custom = bool(e.get("customBrainPrompt"))
            return {
                "text": e["behaviour"] or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                "behaviour": e["behaviour"] or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                "business": e["business"] or DEFAULT_BUSINESS_INSTRUCTIONS,
                "brainPrompt": e.get("brainPrompt") or compose_brain_prompt(
                    behaviour=e.get("behaviour", ""),
                    business=e.get("business", ""),
                    style=e.get("style"),
                ),
                "customBrainPrompt": using_custom,
                "estimatedTokens": e.get("estimatedTokens") or estimate_tokens(e.get("brainPrompt", "")),
                "budgetTokens": e.get("budgetTokens"),
                "updatedAt": e["updatedAt"],
                "present": using_custom or bool(e["behaviour"] or e["business"]),
                "style": e.get("style") or DEFAULT_RESPONSE_STYLE,
                "usingDefaults": not using_custom and not bool(e["behaviour"] or e["business"]),
            }

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store)}


instruction_store = InstructionStore()
