"""Fixed lines for a call placed in a language other than the agent's own.

A language callback runs the agent's published script with another language
pack. Tenant-written fixed lines (the custom farewell, the custom recording
notice) are in the agent's own language, so for that call the platform's
default for the call language is used instead, unless the tenant's line is
already written in that language. The call is never blocked for it; the
substitution is recorded on the call and shown to the tenant as a note.
"""
from __future__ import annotations

import re
from typing import Any

# Unicode blocks per script. Hindi and Marathi share Devanagari, so a line is
# only "in" a language when its script also differs from the agent's own
# language; a Hindi farewell is never assumed to be Marathi.
_SCRIPTS: dict[str, tuple[int, int]] = {
    "hi": (0x0900, 0x097F), "mr": (0x0900, 0x097F), "bn": (0x0980, 0x09FF),
    "pa": (0x0A00, 0x0A7F), "gu": (0x0A80, 0x0AFF), "ta": (0x0B80, 0x0BFF),
    "te": (0x0C00, 0x0C7F), "kn": (0x0C80, 0x0CFF), "ml": (0x0D00, 0x0D7F),
    "en": (0x0041, 0x007A),
}
_PACK_HEADER = re.compile(r"---\s*SPOKEN LANGUAGE\s*\(([^)]+)\)", re.IGNORECASE)


def _base(code: str | None) -> str:
    return str(code or "").split("-")[0].lower()


def _script(text: str) -> tuple[int, int] | None:
    """The dominant script of ``text`` (Latin letters only count when nothing else does)."""
    letters = [ord(c) for c in str(text or "") if c.isalpha()]
    if not letters:
        return None
    counts: dict[tuple[int, int], int] = {}
    for block in set(_SCRIPTS.values()):
        counts[block] = sum(block[0] <= c <= block[1] for c in letters)
    indic = {b: n for b, n in counts.items() if b != _SCRIPTS["en"] and n}
    if indic:
        return max(indic, key=indic.get)
    return _SCRIPTS["en"] if counts[_SCRIPTS["en"]] else None


def written_for(text: str | None, language: str | None, *, own_language: str | None) -> bool:
    """True when ``text`` is usable as-is in ``language`` on a call by an agent whose own language is ``own_language``."""
    if not str(text or "").strip():
        return False
    if _base(language) == _base(own_language):
        return True
    target = _SCRIPTS.get(_base(language))
    own = _SCRIPTS.get(_base(own_language))
    return bool(target and target != own and _script(str(text)) == target)


def agent_language(agent: dict[str, Any]) -> str:
    languages = [str(c) for c in (agent.get("languages") or []) if c]
    return str(agent.get("language") or (languages[0] if languages else "te-IN"))


def disclosure_text_for_call(agent: dict[str, Any], language: str | None) -> str | None:
    """The agent's custom recording notice, or None (platform default for ``language``) when it is in another language."""
    custom = str(agent.get("recording_disclosure_text") or "").strip()
    if not custom or written_for(custom, language, own_language=agent_language(agent)):
        return custom or None
    return None


def brain_language(compiled_text: str | None, fallback: str | None = None) -> str | None:
    match = _PACK_HEADER.search(str(compiled_text or ""))
    return match.group(1).strip() if match else fallback


def language_substitutions(compiled_text: str | None, agent: dict[str, Any], language: str) -> list[dict[str, str]]:
    """Which tenant lines a call in ``language`` replaces with the platform's default."""
    from server.call.call_end_policy import policy_from_brain

    own = brain_language(compiled_text, agent_language(agent)) or agent_language(agent)
    if _base(own) == _base(language):
        return []
    out: list[dict[str, str]] = []
    policy = policy_from_brain(compiled_text, own) or {}
    if policy.get("farewellSource") == "tenant" and not written_for(policy.get("farewell"), language, own_language=own):
        out.append({"line": "farewell", "fromLanguage": own, "toLanguage": language})
    custom = str(agent.get("recording_disclosure_text") or "").strip()
    if agent.get("recording_disclosure_enabled") and custom and not written_for(custom, language, own_language=own):
        out.append({"line": "recording_disclosure", "fromLanguage": own, "toLanguage": language})
    return out


def substitution_note(substitutions: list[dict[str, str]]) -> str | None:
    """One sentence for the tenant, e.g. "Used the standard Hindi goodbye because your custom one is in Telugu. ..."."""
    if not substitutions:
        return None
    from server.call.language_switch import language_name

    target = language_name(substitutions[0]["toLanguage"])
    own = language_name(substitutions[0]["fromLanguage"])
    names = {"farewell": "goodbye", "recording_disclosure": "recording notice"}
    lines = " and ".join(names.get(s["line"], s["line"]) for s in substitutions)
    return (f"Used the standard {target} {lines} because your custom "
            f"{'ones are' if len(substitutions) > 1 else 'one is'} in {own}. "
            f"Add a {target} version in the script.")
