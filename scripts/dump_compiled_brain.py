"""Dump the compiled brain to a file for inspection.

Run: PYTHONIOENCODING=utf-8 python -m scripts.dump_compiled_brain [agent_id]
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

DEFAULT_AGENT = "fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e"
OUT = os.environ.get("DUMP_PATH", "C:/Users/subha/AppData/Local/Temp/opencode/compiled_brain.txt")


async def main() -> int:
    from server.agent.brain_prompt_composer import estimate_tokens
    from server.brain.business_brain_store import (
        assemble_raw_business_prompt,
        business_brain_store,
    )
    from server.brain.business_prompt_optimizer import optimize_business_prompt
    from server.brain.compiled_brain_artifact import (
        assemble_unified_brain,
        platform_body_for_agent_language,
    )
    from server.brain.compiled_brain_service import CompiledBrainService
    from server.brain.platform_brain_store import platform_brain_store
    from server.db.connection import init_db

    agent_id = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AGENT).strip()
    await init_db()

    service = CompiledBrainService()
    platform = await platform_brain_store.get_active()
    lang = await service._primary_language(agent_id)
    sections = await business_brain_store.ensure_default_sections(agent_id)
    raw_prompt, checksum = assemble_raw_business_prompt(sections)
    opt = await optimize_business_prompt(raw_prompt, source_checksum=checksum)
    platform_rules = platform_body_for_agent_language(platform["body"], lang)
    compiled = assemble_unified_brain(
        language=lang,
        script=opt.optimized_business_prompt,
        platform_call_rules=platform_rules,
    )
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(compiled)
    print(f"wrote {OUT}")
    print(f"total {estimate_tokens(compiled):,} tokens, {len(compiled):,} chars")
    print(f"script section: {estimate_tokens(opt.optimized_business_prompt):,} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
