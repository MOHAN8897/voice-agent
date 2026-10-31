"""Measure the Gemini Live instruction for a Telugu call.

The stored snapshots only carry the en-IN pack, so the te-IN pack the live call
actually uses is substituted in to get a faithful number.

Run: PYTHONIOENCODING=utf-8 python -m scripts.gemini_te_in_report
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

VERSION = os.environ.get("BRAIN_VERSION", "cb_v20260929_774bec")
TARGET_MAX = 2500


async def main() -> int:
    from sqlalchemy import text as sql

    from server.agent.brain_prompt_composer import estimate_tokens as T
    from server.db.connection import get_session_factory, init_db
    from server.prompts.agent_voice_rules import spoken_pack_for
    from server.realtime.gemini_audio_session import (
        GEMINI_LIVE_INSTRUCTION_TOKEN_BUDGET,
        build_gemini_audio_session_instructions,
    )

    await init_db()
    f = get_session_factory()
    async with f() as s:
        row = (
            await s.execute(
                sql(
                    "select compiled_text from compiled_brain_snapshots"
                    " where compiled_version = :v"
                ),
                {"v": VERSION},
            )
        ).first()
    brain = row[0] or ""

    # Swap the stored en-IN pack for the te-IN pack this call really uses.
    te = spoken_pack_for("te-IN")
    brain = re.sub(
        r"---\s*SPOKEN LANGUAGE \(en-IN\)\s*---.*?(?=\n---\s)",
        te + "\n\n",
        brain,
        flags=re.S,
    )

    opening = "Hi, nenu Alex, spandana private limited nundi matladutunnanu. Meeku oka moment unda?"
    instruction = build_gemini_audio_session_instructions(
        brain, language="te-IN", direction="outbound", opening_greeting=opening
    )
    total = T(instruction)
    print("=" * 76)
    print(f"te-IN GEMINI LIVE INSTRUCTION   {total:,} tokens")
    print(f"budget                          {GEMINI_LIVE_INSTRUCTION_TOKEN_BUDGET:,}")
    print(f"target                          {TARGET_MAX:,}   over by {total - TARGET_MAX:,}")
    print("=" * 76)
    for needle, label in (
        ("SPOKEN LANGUAGE (TE-IN)", "te-IN language pack"),
        ("CALL END POLICY", "hangup policy"),
        ("STATIC OUTPUT RULES", "static output rules"),
        ("end_call", "end_call tool"),
    ):
        print(f"  {'present' if needle in instruction else 'MISSING':>8}  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
