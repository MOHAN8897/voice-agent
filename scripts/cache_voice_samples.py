"""Warm public catalog samples for a locale; no customer text is stored."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.services.saas.voice_catalog import phone_voice_catalog
from server.services.saas.voice_preview import synthesize_preview


async def main(language):
    limit = asyncio.Semaphore(1)

    async def warm(row):
        async with limit:
            try:
                result = await synthesize_preview(row["sampleText"], provider=row["provider"], voice_id=row["id"], language=row["languageCode"], speed=1)
                return {"voice": row["id"], "bytes": len(result["audio"]), "cacheHit": result["cacheHit"]}
            except Exception as exc:
                return {"voice": row["id"], "error": str(exc)[:200]}

    rows = [row for row in phone_voice_catalog() if row.get("provider") == "gemini" and row.get("languageCode") == language and row.get("sampleText")]
    results = await asyncio.gather(*(warm(row) for row in rows))
    print(json.dumps({"language": language, "samples": results}, ensure_ascii=True))
    if any("error" in row for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="te-IN")
    asyncio.run(main(parser.parse_args().language))
