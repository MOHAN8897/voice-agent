"""Transcript echo filter — same rules as web/lib/echo-guard.ts."""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub(" ", (text or "").lower())).strip()


def is_likely_echo(stt_text: str, assistant_text: str) -> bool:
    user = _normalize(stt_text)
    agent = _normalize(assistant_text)
    if not user or not agent or len(user) < 4:
        return False
    if user in agent:
        return True
    if agent in user and len(agent) > 8:
        return True
    user_words = [w for w in user.split(" ") if len(w) > 1]
    if len(user_words) < 2:
        return False
    agent_words = {w for w in agent.split(" ") if len(w) > 1}
    overlap = sum(1 for w in user_words if w in agent_words)
    return overlap / len(user_words) >= 0.65
