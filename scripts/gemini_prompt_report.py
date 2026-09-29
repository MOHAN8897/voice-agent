"""Measure the FULL Gemini Live system instruction — that is what costs money.

The compiled brain is only part of it: `build_gemini_audio_session_instructions`
wraps it with runtime rules (turn discipline, hangup judgment, voice examples,
direction) and the pinned business script. Optimising the brain alone leaves the
bulk of the spend in place.

Run: PYTHONIOENCODING=utf-8 python -m scripts.gemini_prompt_report
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

TARGET_MIN = 2000
TARGET_MAX = 2500

AGENT_ID = os.environ.get("AGENT_ID", "fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e")


def _tokens(text: str) -> int:
    from server.agent.brain_prompt_composer import estimate_tokens

    return estimate_tokens(text)


async def main() -> int:
    from sqlalchemy import text as sql

    from server.brain.compiled_brain_artifact import assemble_unified_brain
    from server.db.connection import init_db, get_session_factory
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions

    await init_db()
    factory = get_session_factory()
    version = os.environ.get("BRAIN_VERSION", "").strip()
    async with factory() as session:
        if version:
            row = (
                await session.execute(
                    sql(
                        "select compiled_text from compiled_brain_snapshots"
                        " where compiled_version = :v"
                    ),
                    {"v": version},
                )
            ).first()
        else:
            row = (
                await session.execute(
                    sql(
                        "select compiled_text from compiled_brain_snapshots"
                        " order by compiled_at desc limit 1"
                    )
                )
            ).first()
    if not row:
        print("No compiled brain found")
        return 1
    compiled = row[0] or ""

    opening = "Hi, nenu Alex, spandana private limited nundi matladutunnanu. Meeku oka moment unda?"
    instruction = build_gemini_audio_session_instructions(
        compiled,
        language=os.environ.get("SPOKEN_LANGUAGE", "te-IN"),
        direction=os.environ.get("CALL_DIRECTION", "outbound"),
        opening_greeting=opening,
    )

    total = _tokens(instruction)
    print("=" * 78)
    print(f"FULL GEMINI SYSTEM INSTRUCTION   {total:,} tokens")
    print(f"target                           {TARGET_MIN:,}-{TARGET_MAX:,}")
    print(f"must cut                         {100.0 * (1 - TARGET_MAX / total):.0f}%")
    print("=" * 78)

    blocks = _blocks(instruction)
    for t, name, body in sorted(blocks, reverse=True):
        pct = 100.0 * t / total if total else 0
        print(f"  {t:>6,}  {pct:5.1f}%  {name}")
    print()
    print("--- near-duplicate lines (same text appearing 2+ times) ---")
    for line, count in _duplicates(instruction):
        if count > 1 and len(line) > 60:
            print(f"  x{count}  {line[:120]}")
    return 0


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 110:
        return False
    if s.endswith((".", "?", "!", ":", ";")) and not s.startswith(("---", "[", "*", "-")):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.6


def _blocks(text: str) -> list[tuple[int, str, str]]:
    lines = text.splitlines(keepends=True)
    starts = [0]
    offset = 0
    for i, line in enumerate(lines):
        if _is_heading(line):
            if i > 0:
                starts.append(offset)
        offset += len(line)
    starts = sorted(set(starts))
    out: list[tuple[int, str, str]] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        body = text[s:e]
        head = body.strip().splitlines()[0][:60] if body.strip() else "(empty)"
        out.append((_tokens(body), head, body))
    return out


def _duplicates(text: str) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    for line in text.splitlines():
        key = re.sub(r"\s+", " ", line.strip().lower())
        if len(key) < 40:
            continue
        seen[key] = seen.get(key, 0) + 1
    return sorted(((k, v) for k, v in seen.items() if v > 1), key=lambda kv: -kv[1] * len(kv[0]))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
