"""Live-turn structured output schema (CD-016) and streaming spoken_response extractor."""
from __future__ import annotations

from typing import Any

LIVE_TURN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["spoken_response", "memory_update"],
    "properties": {
        "spoken_response": {"type": "string", "maxLength": 4000},
        "memory_update": {
            "type": "object",
            "additionalProperties": False,
            "required": ["operations"],
            "properties": {
                "operations": {
                    "type": "array",
                    "maxItems": 32,
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
                            "key": {"type": "string", "maxLength": 64},
                            "value": {"type": "string", "maxLength": 500},
                        },
                    },
                }
            },
        },
    },
}

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
