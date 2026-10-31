"""Warm the disk cache that serves tenant catalog voice samples.

Each public voice alias is synthesized once per language with the server-owned
greeting, then served from the cache without another provider call. Run this
after enabling a stack or adding voices; scheduled runs are harmless.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(*, languages: list[str], tiers: list[str], concurrency: int, dry_run: bool) -> None:
    from server.config.constants import constants
    from server.db.connection import close_db, init_db
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_preview import synthesize_catalog_preview
    from server.services.saas.voice_stack_profiles import (
        _load_rates_without_fallback,
        load_profile_records,
        public_catalog_profile,
    )

    if not await init_db():
        raise SystemExit("A durable database is required to read the public voice catalog.")
    wanted = set(languages or constants.SUPPORTED_LANGUAGES)
    environment = effective_app_environment()
    try:
        records = await load_profile_records(environment)
        rates = await _load_rates_without_fallback()
        targets: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for tier in sorted(records):
            if tiers and tier not in tiers:
                continue
            profile = public_catalog_profile(tier, records[tier], rates)
            if not profile.get("ready"):
                continue
            for engine in profile.get("engines") or []:
                for model in engine.get("models") or []:
                    for voice in model.get("voices") or []:
                        for language in voice.get("languages") or []:
                            key = (str(voice.get("id") or ""), str(language))
                            if key[0] and language in wanted and key not in seen:
                                seen.add(key)
                                targets.append(key)
        plan = {"environment": environment, "tiers": sorted({tier for tier in records if not tiers or tier in tiers}),
                "languages": sorted(wanted), "samples": len(targets), "dryRun": dry_run}
        if dry_run:
            print(json.dumps(plan, ensure_ascii=True))
            return

        gate = asyncio.Semaphore(max(1, concurrency))

        async def warm(alias: str, language: str) -> dict:
            async with gate:
                try:
                    result = await synthesize_catalog_preview(alias, language)
                    return {"voice": alias, "language": language, "cacheHit": bool(result.get("cacheHit")),
                            "bytes": len(result["audio"])}
                except Exception as exc:
                    return {"voice": alias, "language": language, "error": type(exc).__name__}

        results = await asyncio.gather(*(warm(alias, language) for alias, language in targets))
        failures = [row for row in results if "error" in row]
        plan.update(warmed=len(results) - len(failures), cacheHits=sum(row.get("cacheHit", False) for row in results),
                    failures=failures)
        print(json.dumps(plan, ensure_ascii=True))
        if failures:
            raise SystemExit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", action="append", default=[], help="Language code; repeatable. Defaults to all supported.")
    parser.add_argument("--tier", action="append", default=[], help="Tier; repeatable. Defaults to every enabled tier.")
    parser.add_argument("--concurrency", type=int, default=1, help="Parallel provider calls (default 1).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(languages=args.language, tiers=args.tier, concurrency=args.concurrency, dry_run=args.dry_run))
