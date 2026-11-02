"""Rolling summary from ledger tail — prd/04 async summary every N turns.

The live prompt already carries the most recent turns verbatim (see
``brain_history_turns``), so the summary holds only what has scrolled out of
that window. It used to copy the last few lines, which were always in the
history too: every request carried them twice and older context was lost.
"""
from __future__ import annotations

import asyncio
from typing import Any

from server.call.call_ledger import call_ledger
from server.call.memory_manager import memory_manager
from server.config.env import get_settings
from server.utils.logger import logger

# Composed voice is stateless per request, so it carries more history than realtime.
COMPOSED_HISTORY_TURNS = 10


def brain_history_turns(ctx: Any) -> int:
    """Complete user+assistant turns sent verbatim with each live request."""
    turns = get_settings().brain_context_turns
    if getattr(ctx, "pipeline", None) == "composed_voice":
        turns = max(turns, COMPOSED_HISTORY_TURNS)
    return turns


async def maybe_refresh_rolling_summary(call_id: str, turn_seq: int) -> None:
    settings = get_settings()
    interval = settings.rolling_summary_interval_turns
    if interval <= 0 or turn_seq <= 0 or turn_seq % interval != 0:
        return
    lines = await asyncio.to_thread(call_ledger.read_lines, call_id)
    if not lines:
        return
    from server.call import call_context

    window = brain_history_turns(call_context.get(call_id)) * 2
    older = lines[:-window] if window > 0 else lines
    if not older:
        return
    parts = [f"{row.get('role', 'user')}: {row.get('text', '')}" for row in older[-12:]]
    cap = max(80, settings.rolling_summary_max_tokens * 4)
    # Keep complete utterances; cutting a string tail used to start mid-word
    # and discard who said the surviving fragment. Durable facts live separately.
    selected: list[str] = []
    size = 0
    for part in reversed(parts):
        if size + len(part) + (1 if selected else 0) > cap:
            break
        selected.append(part)
        size += len(part) + (1 if len(selected) > 1 else 0)
    summary = "\n".join(reversed(selected))
    if not summary:
        return
    try:
        await asyncio.to_thread(memory_manager.apply_proposals,
            call_id,
            [{"op": "update_summary", "value": summary}],
            turn_seq=turn_seq,
            source="rolling_summary",
        )
    except Exception as e:
        logger.warning(f"[MEMORY] rolling summary failed call={call_id}: {str(e)[:160]}")
