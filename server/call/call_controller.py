"""Conversation actions are model decisions; connection state belongs to the runtime."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CallAction(str, Enum):
    CONTINUE = "CONTINUE"
    END_CALL = "END_CALL"
    TRANSFER = "TRANSFER"
    VOICEMAIL = "VOICEMAIL"
    CALLBACK = "CALLBACK"


class CallState(str, Enum):
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"
    TRANSFERRING = "transferring"


@dataclass(frozen=True)
class AgentAction:
    action: CallAction
    response: str
    reason: str
    confidence: float

    @classmethod
    def parse(cls, raw: Any) -> AgentAction | None:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                return None
            confidence = float(data["confidence"])
            response, reason = data["response"], data["reason"]
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                return None
            if not isinstance(response, str) or not isinstance(reason, str):
                return None
            if len(response) > 240 or reason not in ACTION_REASONS:
                return None
            return cls(CallAction(data["call_action"]), response.strip(), reason, confidence)
        except (ValueError, TypeError, KeyError):
            return None


ACTION_REASONS = (
    "continue", "goodbye", "goal_complete", "firm_refusal", "opt_out",
    "callback_cancelled", "callback_requested", "transfer_requested", "voicemail",
)

CALL_ACTION_TOOL = {
    "type": "function",
    "name": "call_action",
    "description": (
        "Report conversational intent before speaking a final response. END_CALL for a clear "
        "refusal or completed conversation; CALLBACK only for an explicitly requested callback. "
        "A withdrawal overrides an earlier callback. Do not end for a bare okay/thanks, a pause, "
        "or a follow-up question. The application plays response and owns hangup/transfer. "
        "Wait for the tool result; never claim an unavailable transfer or unconfirmed callback."
    ),
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "call_action": {"type": "string", "enum": [a.value for a in CallAction]},
            "response": {"type": "string", "maxLength": 240},
            "reason": {"type": "string", "enum": list(ACTION_REASONS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["call_action", "response", "reason", "confidence"],
    },
}


class CallLifecycleController:
    def __init__(self) -> None:
        self.state = CallState.ACTIVE
        self.reason = ""
        self.callback_cancelled = False

    def request(self, action: AgentAction, *, caller_speaking: bool = False) -> str | None:
        """Return a rejection code or accept. No transcript keyword matching here."""
        if self.state != CallState.ACTIVE:
            return "call_not_active"
        if action.confidence < 0.85:
            return "uncertain_intent"
        if action.reason in {"opt_out", "firm_refusal", "callback_cancelled"}:
            self.callback_cancelled = True
        if action.action == CallAction.END_CALL:
            if action.reason not in {"goodbye", "goal_complete", "firm_refusal", "opt_out", "callback_cancelled"}:
                return "invalid_end_reason"
            if caller_speaking:
                return "caller_still_talking"
            self.state, self.reason = CallState.ENDING, action.reason
        elif action.action in {CallAction.TRANSFER, CallAction.VOICEMAIL}:
            # No provider handoff implementation is configured in this runtime.
            return "action_unavailable"
        elif action.action == CallAction.CALLBACK and self.callback_cancelled:
            return "callback_withdrawn"
        return None

    def resume(self) -> None:
        if self.state == CallState.ENDING:
            self.state, self.reason = CallState.ACTIVE, ""

    def end(self, reason: str = "") -> None:
        self.state = CallState.ENDED
        self.reason = reason or self.reason
