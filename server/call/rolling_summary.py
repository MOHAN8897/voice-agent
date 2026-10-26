"""Rolling summary from ledger tail — prd/04 async summary every N turns."""
from __future__ import annotations

import asyncio

from server.call.call_ledger import call_ledger
from server.call.memory_manager import memory_manager
from server.config.env import get_settings
from server.utils.logger import logger


async def maybe_refresh_rolling_summary(call_id: str, turn_seq: int) -> None:
    settings = get_settings()
    interval = settings.rolling_summary_interval_turns
    if interval <= 0 or turn_seq <= 0 or turn_seq % interval != 0:
        return
    lines = await asyncio.to_thread(call_ledger.read_lines, call_id)
    if not lines:
        return
    tail = lines[-12:]
    parts = [f"{row.get('role', 'user')}: {row.get('text', '')}" for row in tail]
    text = "\n".join(parts).strip()
    if not text:
        return
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
