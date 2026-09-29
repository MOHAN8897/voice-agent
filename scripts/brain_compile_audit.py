"""Measure the compiled brain artifact that agent creation actually produces.

`CompiledBrainService.compile_for_agent` ends in `assemble_unified_brain`, so this
replays that same assembly read-only (no snapshot row, no active-pointer write)
and reports the total plus a per-section breakdown.

Run: PYTHONIOENCODING=utf-8 python -m scripts.brain_compile_audit [agent_id]
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

TARGET_MAX = 3000
DEFAULT_AGENT = "fb93adcd-2f61-4b69-b1b7-f34ed3a61b7e"

# Sections the agent must not lose. Call end policy is listed because the hangup
# story lives there and is explicitly out of scope for compression.
PROTECTED = ("CALL END POLICY",)


def _tokens(text: str) -> int:
    from server.agent.brain_prompt_composer import estimate_tokens

    return estimate_tokens(text)


def _sections(text: str) -> list[tuple[str, str]]:
    marks = list(re.finditer(r"(?:^|\n)---\s*(.+?)\s*---\s*\n", text))
    if not marks:
        return [("(no sections)", text)]
    out: list[tuple[str, str]] = []
    if marks[0].start() > 0:
        out.append(("(preamble)", text[: marks[0].start()]))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.start() : end]))
    return out


async def main() -> int:
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
    if not await init_db():
        print("DATABASE_URL not configured")
        return 1

    service = CompiledBrainService()
    platform = await platform_brain_store.get_active()
    lang = await service._primary_language(agent_id)
    sections = await business_brain_store.ensure_default_sections(agent_id)
    raw_prompt, source_checksum = assemble_raw_business_prompt(sections)
    opt = await optimize_business_prompt(raw_prompt, source_checksum=source_checksum)
    platform_rules = platform_body_for_agent_language(platform["body"], lang)
    compiled = assemble_unified_brain(
        language=lang,
        script=opt.optimized_business_prompt,
        platform_call_rules=platform_rules,
    )

    total = _tokens(compiled)
    print("=" * 78)
    print(f"agent            {agent_id}")
    print(f"language         {lang}")
    print(f"COMPILED BRAIN   {total:,} tokens   ({len(compiled):,} chars)")
    print(f"target           <= {TARGET_MAX:,}   over by {total - TARGET_MAX:,}")
    print("=" * 78)
    parts = _sections(compiled)
    for name, body in sorted(parts, key=lambda p: -_tokens(p[1])):
        t = _tokens(body)
        flag = "  <-- protected" if name.upper() in PROTECTED else ""
        print(f"  {t:>6,}  {100.0 * t / total:5.1f}%  {name}{flag}")
    print()
    titles = [n for n, _ in parts]
    print(f"sections ({len(titles)}): {', '.join(titles)}")
    return 0 if total <= TARGET_MAX else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
