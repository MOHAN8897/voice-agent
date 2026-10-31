"""Live Standard classifier through an isolated server/carrier simulation.

Run from the repository root with .venv/Scripts/python.exe -X utf8 <this file>.
Speech synthesis, business reply and the carrier are substituted; the close
classifier, close gate, PSTN loop, executor and lifecycle use the current code.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


async def main() -> None:
    import pytest

    from server.config.env import Settings, get_settings
    from server.providers.sarvam_llm import SarvamLLMAdapter

    # Load the already-configured credential into memory before isolating data.
    # It is never written to an artifact, log, environment variable or argument.
    configured = SarvamLLMAdapter()
    adapter = SarvamLLMAdapter(api_key=configured._api_key())
    Settings.model_config["env_file"] = None
    os.environ.pop("DATABASE_URL", None)
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="natural-close-live-")
    os.environ["SAAS_AUTH_ENABLED"] = "false"
    os.environ["FX_RATE_LIVE"] = "false"
    get_settings.cache_clear()

    from server.tests.test_close_classifier_handoff import CLOSE_CASES, run_voice_simulation

    results = []
    cases = [(language, user, closing, False) for language, user, closing in CLOSE_CASES]
    cases.append(("te-IN", "అంతే అంతే థ్యాంక్ యూ", True, True))
    sources = [ROOT / "server/call" / name for name in (
        "close_classifier.py", "live_turn_orchestrator.py", "end_call_validate.py",
        "close_call_executor.py", "call_lifecycle_service.py", "natural_hangup.py",
        "caller_intent.py", "close_decision.py", "call_context.py",
    )]
    sources.extend([
        ROOT / "server/services/pstn_voice_core.py",
        ROOT / "server/brain/compiled_brain_artifact.py",
        ROOT / "server/call/call_end_policy.py",
        ROOT / "server/services/saas/callback_request_service.py",
        ROOT / "server/services/vobiz_pstn_bridge.py",
    ])
    source_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    for language, user, closing, retry in cases:
        with pytest.MonkeyPatch.context() as patcher:
            try:
                result = await run_voice_simulation(
                    patcher, language, user, closing, adapter=adapter, retry_attempt=retry,
                )
            except (AssertionError, RuntimeError, TimeoutError, ValueError) as exc:
                result = {
                    "language": language, "caller": user, "expected_close": closing,
                    "passed": False, "error_type": type(exc).__name__,
                }
            results.append(result)
            result["retry_attempt"] = retry
            print(json.dumps(result, ensure_ascii=False), flush=True)
    destination = Path(__file__).with_name("live-results.json")
    destination.write_text(json.dumps({
        "model": "sarvam-105b-conversations",
        "scope": "live classifier; simulated business speech, playback and carrier",
        "source_sha256": source_hashes,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = sum(not result["passed"] for result in results)
    print(f"{len(results) - failures}/{len(results)} passed", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
