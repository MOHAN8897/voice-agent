"""Refresh supplier voices; --snapshot regenerates public documentation facts only."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.providers.voice_inventory import DOCUMENTS, SNAPSHOT, parse_document_catalogs, refresh_inventory


async def main(snapshot: bool) -> None:
    if snapshot:
        import httpx
        previous = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            responses = await asyncio.gather(*(client.get(url) for url in DOCUMENTS.values()))
        for response in responses:
            response.raise_for_status()
        data = parse_document_catalogs(dict(zip(DOCUMENTS, (response.text for response in responses))))
        # API-only inventories are not part of the public documentation pages;
        # keep the last verified API rows instead of deleting them on a docs refresh.
        for provider in ("gemini", "cartesia"):
            prior = (previous.get(provider) or {}).get("voices")
            if prior and not data.get(provider, {}).get("voices"):
                data.setdefault(provider, {})["voices"] = prior
        data.update(schemaVersion=1, sources=DOCUMENTS, checkedAt=datetime.now(timezone.utc).isoformat())
        SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Updated public documentation snapshot.")
    else:
        print(json.dumps(await refresh_inventory()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="store_true")
    asyncio.run(main(parser.parse_args().snapshot))
