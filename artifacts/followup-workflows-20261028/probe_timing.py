"""Synthetic timing requests using actual saved model selections; no dialing or TTS."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from server.services.saas.followup_policy import FollowUpConfig, timing_model_snapshot
from server.services.saas.followup_service import _extract_time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
AT = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)


async def main():
    selections = {}
    for path in sorted((ROOT / "data/calls").glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        try:
            saved = (json.loads(path.read_text(encoding="utf-8")).get("resolved_stack") or {}).get("llm") or {}
            if saved.get("provider") in ("sarvam", "gemini") and saved["provider"] not in selections:
                selections[saved["provider"]] = timing_model_snapshot(SimpleNamespace(**saved))
        except (ValueError, TypeError, KeyError):
            continue
    rows = []
    for kind, selection in selections.items():
        timing_at = AT + timedelta(minutes=5)
        split = [{"role": "user", "text": "Call me later", "at": AT.isoformat()},
                 {"role": "assistant", "text": "When should I call you?", "at": AT.isoformat()},
                 {"role": "user", "text": "ఆరు గంటల తర్వాత", "at": timing_at.isoformat()}]
        unagreed = [{"role": "assistant", "text": "Would six hours work?", "at": AT.isoformat()},
                    {"role": "user", "text": "I am not sure yet", "at": AT.isoformat()}]
        cases = [("english_relative", "Please call me after six hours.", AT + timedelta(hours=6), []),
                 ("telugu_relative", "ఆరు గంటల తర్వాత నాకు కాల్ చేయండి.", AT + timedelta(hours=6), []),
                 ("hindi_relative", "छह घंटे बाद मुझे फोन करना।", AT + timedelta(hours=6), []),
                 ("vague_requires_review", "Call me later sometime.", None, []),
                 ("split_telugu_uses_timing_utterance_timestamp", "Call me later", timing_at + timedelta(hours=6), split),
                 ("agent_suggestion_without_agreement", "Call me later", None, unagreed)]
        for name, text, expected, recent in cases:
            job = SimpleNamespace(created_at=AT, payload={"requestText": text, "requestedAt": AT.isoformat(), "llm": selection, "recentTurns": recent})
            try:
                actual = await _extract_time(job, FollowUpConfig(timezone="Asia/Kolkata"))
                result = {"modelSource": kind, "case": name, "pass": actual == expected,
                          "expected": expected.isoformat() if expected else None, "actual": actual.isoformat() if actual else None}
            except Exception as exc:
                result = {"modelSource": kind, "case": name, "pass": False, "errorType": type(exc).__name__}
            rows.append(result)
            print(json.dumps(result), flush=True)
    (OUT / "live-timing-probes.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if not rows or not all(r["pass"] for r in rows):
        raise SystemExit(1)


asyncio.run(main())
