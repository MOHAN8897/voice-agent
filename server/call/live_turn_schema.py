"""Live-turn structured output schema (CD-016) and streaming spoken_response extractor."""
from __future__ import annotations

import re
from typing import Any

from server.call.close_decision import parse_close_proposal
from server.services.voice_pipeline_limits import LIVE_REPLY_MAX_CHARS

# end_call leads the object so the decision is readable before any spoken text,
# and the proof order is evidence -> intent -> decision. The server owns the
# farewell: a close turn never supplies one, and its spoken text is withheld
# until the gate decides.
LIVE_TURN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["end_call", "order_claimed", "spoken_response", "memory_update"],
    "properties": {
        "end_call": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "evidence",
                "reason",
                "decision",
                "remaining_request",
                "contact_preference",
            ],
            "properties": {
                # Exact words copied from the caller's current turn, or "".
                "evidence": {
                    "type": "string",
                    "maxLength": 200,
                    "description": (
                        "Exact words from the caller's CURRENT turn that prove the intent. "
                        "Copy them; never paraphrase or quote an earlier turn."
                    ),
                },
                "reason": {
                    "type": "string",
                    "enum": [
                        "none",
                        "goodbye",
                        "firm_refusal",
                        "not_interested",
                        "goal_complete",
                        "abuse",
                        "out_of_scope",
                    ],
                    "description": "The caller's intent, proven by evidence.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["continue", "clarify", "close", "callback"],
                    "description": (
                        "Default is continue. Close only when evidence proves a goodbye, "
                        "stop-contact request, clear decline, or completed objective. A "
                        "price, service or product question is never a reason to close."
                    ),
                },
                # What the caller still wants, if anything; blocks a close.
                "remaining_request": {"type": "string", "maxLength": 240},
                "contact_preference": {
                    "type": "string",
                    "enum": ["none", "end_call", "do_not_call", "callback"],
                },
            },
        },
        # Readable before spoken_response, so an order claim can be held until
        # the server has proof. True only after CONFIRM_ORDER returned status ok.
        "order_claimed": {
            "type": "boolean",
            "description": (
                "True only when this turn speaks an order/booking confirmation, "
                "which requires CONFIRM_ORDER to have returned status ok."
            ),
        },
        "spoken_response": {"type": "string", "maxLength": LIVE_REPLY_MAX_CHARS},
        "memory_update": {
            "type": "object",
            "additionalProperties": False,
            "required": ["operations"],
            "properties": {
                "operations": {
                    "type": "array",
                    # Three short facts must fit alongside the reply floor; the
                    # model may not spend the turn budget on a memory dump.
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["op", "key", "value"],
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": [
                                    "set_fact",
                                    "set_preference",
                                    "append_context",
                                    "update_summary",
                                ],
                            },
                            "key": {"type": "string", "maxLength": 48},
                            "value": {"type": "string", "maxLength": 150},
                        },
                    },
                }
            },
        },
    },
}

# The decision is written after the evidence and reason, before any spoken
# text. Scanning stops at the spoken_response key, so a decision-shaped fragment
# inside the reply can never open the gate early. JSON-escaped copies of the
# caller's words cannot match: their closing quote is preceded by a backslash.
_PREVIEW_DECISION = re.compile(r'"decision"\s*:\s*"(continue|clarify|close|callback)"')
_PREVIEW_ORDER_CLAIM = re.compile(r'"order_claimed"\s*:\s*true')

TEXT_FORMAT_LIVE_TURN: dict[str, Any] = {
    "format": {
        "type": "json_schema",
        "name": "live_turn",
        "strict": True,
        "schema": LIVE_TURN_JSON_SCHEMA,
    }
}


class SpokenResponseExtractor:
    """
    Incrementally extract `spoken_response` from a JSON object stream so TTS can
    start before `memory_update` is complete. If the stream is plain text, pass it through.
    """

    def __init__(self) -> None:
        self._raw: list[str] = []
        self._mode: str = "unknown"  # unknown | plain | json
        self._seek: str = "key"  # key | colon | quote | string | done
        self._key_buf = ""
        self._escape = False
        self._spoken: list[str] = []
        self._emitted = 0
        self._preview_decision: str | None = None

    @property
    def raw_text(self) -> str:
        return "".join(self._raw)

    @property
    def spoken_text(self) -> str:
        if self._mode == "plain":
            return self.raw_text
        return "".join(self._spoken)

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._raw.append(chunk)
        if self._mode == "unknown":
            combined = "".join(self._raw).lstrip()
            if not combined:
                return ""
            if combined[0] != "{":
                self._mode = "plain"
                return combined
            self._mode = "json"
            return self._consume_json(combined)
        if self._mode == "plain":
            return chunk
        return self._consume_json(chunk)

    def _consume_json(self, chunk: str) -> str:
        newly: list[str] = []
        for ch in chunk:
            if self._seek == "done":
                break
            if self._seek == "key":
                self._key_buf += ch
                if '"spoken_response"' in self._key_buf:
                    self._seek = "colon"
                    self._key_buf = ""
            elif self._seek == "colon":
                if ch.isspace():
                    continue
                if ch == ":":
                    self._seek = "quote"
                else:
                    self._seek = "key"
            elif self._seek == "quote":
                if ch.isspace():
                    continue
                if ch == '"':
                    self._seek = "string"
                    self._escape = False
                else:
                    self._seek = "key"
            elif self._seek == "string":
                if self._escape:
                    mapped = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(ch, ch)
                    self._spoken.append(mapped)
                    newly.append(mapped)
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._seek = "done"
                else:
                    self._spoken.append(ch)
                    newly.append(ch)
        out = "".join(newly)
        self._emitted += len(out)
        return out

    def parse_memory_update(self) -> dict[str, Any]:
        payload = self._parsed_object()
        if not payload:
            return {"operations": []}
        update = payload.get("memory_update")
        if not isinstance(update, dict):
            return {"operations": []}
        ops = update.get("operations")
        if not isinstance(ops, list):
            return {"operations": []}
        return {"operations": ops}

    def preview_decision(self) -> str | None:
        """The close decision as soon as the JSON head makes it readable.

        None means unknown (or not in schema order); callers must treat unknown
        as 'hold', never as 'safe to speak a farewell'.
        """
        if self._preview_decision is not None:
            return self._preview_decision
        if self._mode != "json":
            return None
        head = self.raw_text
        spoken_at = head.find('"spoken_response"')
        if spoken_at >= 0:
            head = head[:spoken_at]
        if '"end_call"' not in head:
            return None
        match = _PREVIEW_DECISION.search(head)
        if match:
            self._preview_decision = match.group(1)
        return self._preview_decision

    def preview_order_claim(self) -> bool | None:
        """Whether the turn claims a confirmed order, read before speech.

        None means the flag is not readable yet; callers must treat unknown as
        'not allowed to claim' while the text is held, never as safe.
        """
        if self._mode != "json":
            return None
        head = self.raw_text
        spoken_at = head.find('"spoken_response"')
        if spoken_at >= 0:
            head = head[:spoken_at]
        if '"order_claimed"' not in head:
            return None
        return bool(_PREVIEW_ORDER_CLAIM.search(head))

    def parse_end_call(self) -> dict[str, Any]:
        payload = self._parsed_object()
        raw = payload.get("end_call") if payload else None
        if not isinstance(raw, dict):
            return {
                "should_end": False,
                "decision": "continue",
                "reason": "none",
                "evidence": "",
                "remaining_request": "",
                "contact_preference": "",
                "farewell": "",
                "conflict": False,
            }
        proposal = parse_close_proposal(raw)
        return {
            "should_end": proposal.should_end,
            "decision": proposal.decision,
            "reason": proposal.reason,
            "evidence": proposal.evidence,
            "remaining_request": proposal.remaining_request,
            "contact_preference": proposal.contact_preference,
            "farewell": proposal.farewell,
            "conflict": proposal.conflict,
        }

    def structured_parse_failed(self) -> bool:
        """True when structured JSON was required but missing or invalid (SLO/parse fallback)."""
        if self._mode == "plain":
            return True
        if self._mode != "json":
            return True
        return self._parsed_object() is None

    def _parsed_object(self) -> dict[str, Any] | None:
        import json

        raw = self.raw_text.strip()
        if not raw.startswith("{"):
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                payload = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return payload if isinstance(payload, dict) else None
