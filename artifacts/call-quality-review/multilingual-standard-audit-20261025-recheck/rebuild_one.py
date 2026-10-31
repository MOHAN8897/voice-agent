"""Rebuild one cached agent with the current compiler, then re-run its sessions."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_audit as R  # noqa: E402

BUSINESS = sys.argv[1] if len(sys.argv) > 1 else "course"
LANGUAGE = sys.argv[2] if len(sys.argv) > 2 else "te-IN"
FOLDER = R.OUT / "agents" / f"{BUSINESS}-{LANGUAGE}"


async def main() -> None:
    settings, app = R.setup()
    import httpx

    brief = next(item for item in R.BRIEFS if item["key"] == BUSINESS)
    corpus = await R.translate_corpus(LANGUAGE)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost", timeout=300
    ) as client:
        build = await R.build_agent(client, brief, LANGUAGE)
    print("build status:", build.get("status"), "http:", build.get("http_status"), flush=True)
    print(
        "compiled has obsolete price:",
        "3999" in build.get("compiled", ""),
        "active price:",
        "4999" in build.get("compiled", ""),
        flush=True,
    )
    if build.get("status") != "ready":
        print(json.dumps(build.get("response"), ensure_ascii=True)[:800], flush=True)
        return
    VoiceLoop = R.install_runtime_instrumentation(settings)
    semaphore = asyncio.Semaphore(3)

    async def one(integration: bool, scenario: str) -> dict:
        async with semaphore:
            return await R.run_session(build, corpus, integration, scenario, VoiceLoop)

    results = await asyncio.gather(
        *(
            one(integration, scenario)
            for integration in (False, True)
            for scenario in R.SCENARIOS
        )
    )
    print(
        json.dumps(
            {
                "sessions": len(results),
                "ended": sum(bool(row["carrier"]) for row in results),
                "open": [row["key"] for row in results if not row["carrier"]],
                "spoke_obsolete_price": [
                    row["key"]
                    for row in results
                    for turn in row["turns"]
                    if "3999" in (turn["spoken"] or "")
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
