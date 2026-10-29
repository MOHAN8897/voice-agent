"""Isolated runtime for live simulator runs. Never touches customer tables.

Each run gets its own Postgres schema seeded with the current tier, billing and
platform-config rows, so the real stack resolver and orchestrator run unchanged
while every call, lead, memory and DND write lands in throwaway storage.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
import re
import shutil
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts" / "call-quality-review"
ACTOR = ContextVar("sim_actor", default="setup")
CASE = ContextVar("sim_case", default=None)
REQUESTS: list[dict] = []

_SCHEMA_RE = re.compile(r"sim_[0-9a-f]{32}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# .env keys tried in order; a later one is used once an earlier one runs out of credits.
SARVAM_ENV_KEYS = ("SARVAM_API_KEY", "SARVAM_API_KEY_1")
_sarvam_keys: list[str] = []


def use_env_sarvam_key() -> None:
    """Test-process only: prefer the .env Sarvam keys over the admin-panel key.

    Nothing is written to the secrets store; the override lives in this process's
    memory and only exists when a run explicitly asks for it.
    """
    from dotenv import dotenv_values
    from server.services.dev_secrets_store import dev_secrets_store

    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    _sarvam_keys[:] = [k for k in (str(values.get(n) or "").strip() for n in SARVAM_ENV_KEYS) if k]
    if not _sarvam_keys:
        raise RuntimeError("No SARVAM_API_KEY / SARVAM_API_KEY_1 in .env to use for this run")
    if getattr(dev_secrets_store.effective_secret, "_sim_sarvam", False):
        return
    original = dev_secrets_store.effective_secret

    def effective_secret(field: str):
        return _sarvam_keys[0] if field == "sarvam_api_key" else original(field)

    effective_secret._sim_sarvam = True
    dev_secrets_store.effective_secret = effective_secret


def rotate_sarvam_key() -> bool:
    """Move to the next .env key after a credits error. False when none remain."""
    if len(_sarvam_keys) < 2:
        return False
    _sarvam_keys.pop(0)
    return True


def is_credits_error(text: str | None) -> bool:
    return bool(text) and ("402" in text or "insufficient_quota" in text or "No credits" in text)


async def setup(out_dir: Path, *, schema: str | None = None, sarvam_key_source: str = "runtime") -> dict:
    """Point the app at a fresh (or resumed) owned schema and record Sarvam requests."""
    if sarvam_key_source == "env":
        use_env_sarvam_key()
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from server.config.env import get_settings
    from server.db import connection
    from server.db.models.entities import Base, ConfigVersion, TierAssignment
    from server.db.models.saas_models import BillingRateVersion
    from server.db.tier_store import load_tier_cache
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    parsed = urlsplit(settings.database_url or "")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Refusing a simulator run against a non-local database")
    for key in ("sarvam_api_key", "gemini_api_key", "openai_api_key", "cartesia_api_key", "gnani_api_key"):
        value = dev_secrets_store.effective_secret(key) or getattr(settings, key, None)
        if value and hasattr(settings, key):
            setattr(settings, key, value)
    await connection.init_db()
    await load_tier_cache()
    async with connection.get_session_factory()() as db:
        rows = [*(await db.scalars(select(TierAssignment))).all(),
                *(await db.scalars(select(BillingRateVersion))).all(),
                *(await db.scalars(select(ConfigVersion).where(ConfigVersion.resource_type.in_(
                    ("platform_languages", "voice_stack", "provider_registry"))))).all()]
        snapshots = [(type(r), {c.key: getattr(r, c.key) for c in r.__table__.columns}) for r in rows]
    resume = schema is not None
    schema = schema or "sim_" + uuid.uuid4().hex
    if not _SCHEMA_RE.fullmatch(schema):
        raise RuntimeError("Simulator schema must be an owned sim_<hex> schema")
    admin = connection.get_engine()
    async with admin.begin() as db:
        exists = await db.scalar(text("SELECT 1 FROM pg_namespace WHERE nspname=:n"), {"n": schema})
        if resume and not exists:
            raise RuntimeError("Simulator schema to resume no longer exists")
        if not exists:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(connection._to_async_url(settings.database_url), pool_pre_ping=True,
                                 connect_args={"server_settings": {"search_path": schema}},
                                 pool_size=8, max_overflow=4)
    import server.db.models as models
    for item in pkgutil.iter_modules(models.__path__):
        importlib.import_module("server.db.models." + item.name)
    if not resume:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
    connection._engine = engine
    connection._session_factory = async_sessionmaker(engine, expire_on_commit=False)
    if not resume:
        async with connection.get_session_factory()() as db:
            for cls, values in snapshots:
                db.add(cls(**values))
            await db.commit()
    await admin.dispose()

    data = out_dir / "isolated-data"
    data.mkdir(parents=True, exist_ok=True)
    for name in ("saas_universal_phone_stack.json", "platform_languages.json", "provider_voice_inventory.json"):
        source = settings.data_path / name
        if source.is_file() and not (data / name).exists():
            shutil.copy2(source, data / name)
    settings.data_dir = str(data)
    os.environ["DATA_DIR"] = str(data)
    from server.call import redis_memory_cache
    redis_memory_cache._PREFIX = schema + ":memory:"
    from server.services.r2_storage import r2_storage
    r2_storage.is_configured = lambda: False
    import server.call.post_call_transcription as transcription
    transcription.schedule_post_call_transcription = lambda _call: None

    logging.getLogger().setLevel(logging.ERROR)
    for name in ("httpx", "httpcore", "google_genai", "server"):
        logging.getLogger(name).setLevel(logging.ERROR)
    from server.utils.logger import RedactingFormatter, logger
    logger.handlers.clear()
    handler = logging.FileHandler(out_dir / "runtime.log", encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

    from server.providers.sarvam_llm import SarvamLLMAdapter
    original_body = SarvamLLMAdapter._request_body

    def observed_body(self, **kwargs):
        body = original_body(self, **kwargs)
        REQUESTS.append({"case": CASE.get(), "actor": ACTOR.get(), "body": body})
        return body

    if not getattr(SarvamLLMAdapter._request_body, "_sim_observed", False):
        observed_body._sim_observed = True
        SarvamLLMAdapter._request_body = observed_body
    return {"schema": schema, "data_dir": str(data)}


async def sarvam_preflight(model: str) -> None:
    """Fail fast on an account problem instead of recording every turn as an agent failure."""
    import httpx
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    while True:
        key = dev_secrets_store.effective_secret("sarvam_api_key") or get_settings().sarvam_api_key or ""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.sarvam.ai/v1/chat/completions",
                                         headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
                                         json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 4})
        if response.status_code not in {401, 402, 403}:
            return
        if response.status_code == 402 and rotate_sarvam_key():
            continue
        raise RuntimeError(f"Sarvam account cannot serve requests (HTTP {response.status_code}): {response.text[:200]}")


def require_sarvam_brain(stack: Any) -> None:
    """The simulator measures the Sarvam brain; never silently swap the model under test."""
    if getattr(stack.llm, "provider", None) != "sarvam":
        raise RuntimeError(f"Resolved LLM is {stack.llm.provider}, not Sarvam; refusing to run")
