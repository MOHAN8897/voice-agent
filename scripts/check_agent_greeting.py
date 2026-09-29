"""Why did the outbound call have no opening greeting?

Checks, for one agent: what the prewarm greeting extractor returns for the
outbound direction, and what the telephony profile carries.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The brain is Telugu; the Windows console codec cannot print it.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

AGENT_ID = os.environ.get("AGENT_ID", "fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e")


async def main() -> int:
    from sqlalchemy import text

    from server.db.connection import init_db

    if not await init_db():
        print("DATABASE_URL is not configured")
        return 1

    from server.db.connection import get_session_factory

    factory = get_session_factory()
    async with factory() as conn:
        # 1. Telephony profile greeting (the field the outbound path reads).
        row = await conn.execute(
            text(
                "select greeting_phrase, business_hours, timezone, inbound_enabled,"
                " outbound_enabled from agent_telephony_profiles where agent_id = :a"
            ),
            {"a": AGENT_ID},
        )
        profile = row.mappings().first()
        print("--- telephony profile ---")
        print("  greeting_phrase     :", repr((profile or {}).get("greeting_phrase")))
        print("  inbound_enabled     :", (profile or {}).get("inbound_enabled"))
        print("  outbound_enabled    :", (profile or {}).get("outbound_enabled"))

        # 2. The published brain text the greeting extractor consumes.
        rows = await conn.execute(
            text(
                "select optimized_prompt, status from business_brain_versions"
                " where agent_id = :a order by created_at desc limit 1"
            ),
            {"a": AGENT_ID},
        )
        brain = rows.mappings().first()
        brain_text = (brain or {}).get("optimized_prompt") or ""
        print("\n--- published brain ---")
        print("  found               :", bool(brain))
        print("  status              :", (brain or {}).get("status"))
        print("  length              :", len(brain_text))
        for marker in ("OPENING", "GREETING", "opening", "greeting"):
            if marker in brain_text:
                idx = brain_text.index(marker)
                print(f"  contains {marker!r} at {idx}: {brain_text[idx:idx+120]!r}")
                break
        else:
            print("  contains NO opening/greeting marker")

    # 3. What the extractor actually returns for each direction.
    from server.services.pstn_prewarm import extract_prewarm_greeting  # type: ignore

    print("\n--- extract_prewarm_greeting ---")
    for direction in ("outbound", "inbound"):
        try:
            got = extract_prewarm_greeting(brain_text, "te-IN", direction=direction)
        except Exception as exc:  # noqa: BLE001
            got = f"<error: {exc}>"
        verdict = "OK" if (isinstance(got, str) and got.strip()) else "*** EMPTY -> NO GREETING WILL BE SPOKEN ***"
        print(f"  {direction:9s}: {got!r}   {verdict}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
