"""Re-run one scenario against cached ready builds with the current source.

The full matrix is expensive and mostly cached; after a targeted fix this
re-executes only the affected scenario files (delete them first) while reusing
the archived builds and translated caller corpus.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_audit as R  # noqa: E402

SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "4_abuse"
KEY_FILTER = sys.argv[2] if len(sys.argv) > 2 else ""


async def main() -> None:
    settings, _app = R.setup()
    builds = []
    for path in sorted((R.OUT / "agents").glob("*/build.json")):
        build = json.loads(path.read_text(encoding="utf-8"))
        if build.get("status") == "ready" and (not KEY_FILTER or build.get("language") == KEY_FILTER):
            builds.append(build)
    corpora = {}
    for language in sorted({build["language"] for build in builds}):
        corpora[language] = await R.translate_corpus(language)
    VoiceLoop = R.install_runtime_instrumentation(settings)
    semaphore = asyncio.Semaphore(3)

    async def one(build: dict, integration: bool) -> dict:
        async with semaphore:
            return await R.run_session(
                build, corpora[build["language"]], integration, SCENARIO, VoiceLoop
            )

    results = await asyncio.gather(
        *(one(build, integration) for build in builds for integration in (False, True))
    )
    print(
        json.dumps(
            {
                "scenario": SCENARIO,
                "sessions": len(results),
                "ended": sum(bool(row["carrier"]) for row in results),
                "open": [row["key"] for row in results if not row["carrier"]],
                "harness_errors": [row["key"] for row in results if row["status"] != "completed"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
