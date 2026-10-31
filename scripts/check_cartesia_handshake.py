"""Inspect Cartesia's TTS handshake rejection without placing a call."""
import asyncio
import json

from server.config.env import get_settings
from server.services.cartesia_tts_ws import connect_cartesia_tts_ws
from server.services.dev_secrets_store import dev_secrets_store


async def main():
    try:
        async with connect_cartesia_tts_ws() as _:
            print(json.dumps({"ok": True}))
    except Exception as exc:
        response = getattr(exc, "response", None)
        raw = getattr(response, "body", b"")
        detail = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        for key in (get_settings().cartesia_api_key, dev_secrets_store.effective_secret("cartesia_api_key")):
            if key:
                detail = detail.replace(key, "[redacted]")
        print(json.dumps({"ok": False, "status": getattr(response, "status_code", None),
                          "detail": detail[:1500], "error": str(exc)[:200]}))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=15))
