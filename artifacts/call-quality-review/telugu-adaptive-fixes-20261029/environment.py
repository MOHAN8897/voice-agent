"""Isolated, persistent runtime for a live-model audit. Never uses customer tables."""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import logging
import os
import pkgutil
import shutil
import subprocess
import uuid
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CASE = ContextVar("audit_case", default=None)
ACTOR = ContextVar("audit_actor", default="setup")
REQUESTS: list[dict] = []
NETWORK: list[dict] = []


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def source_manifest():
    files = list((ROOT / "server").rglob("*.py"))
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if "__pycache__" not in str(p)}


def business_inputs():
    """Reuse only literal business input data, not the old runner's global patches."""
    path = ROOT / "artifacts/call-quality-review/telugu-agentic-audit-20261029/create_agents.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.Assign)
            and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)
            and not any(isinstance(n, (ast.Call, ast.Attribute)) for n in ast.walk(node.value))]
    values: dict = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), {}, values)
    return values["BUSINESSES"]


async def setup():
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from server.config.env import get_settings
    from server.db import connection
    from server.db.models.entities import Base, TierAssignment, ConfigVersion
    from server.db.models.saas_models import BillingRateVersion
    from server.db.tier_store import load_tier_cache
    from server.providers.resolver import resolve_stack
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    parsed = urlsplit(settings.database_url or "")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path.lstrip("/") != "voice_agent":
        raise RuntimeError("Refusing an audit against a non-local database")
    original_data = settings.data_path
    for key in ("sarvam_api_key", "gemini_api_key", "openai_api_key"):
        value = dev_secrets_store.effective_secret(key) or getattr(settings, key, None)
        if value:
            setattr(settings, key, value)
    await connection.init_db()
    await load_tier_cache()
    stack = resolve_stack(tier="medium", language="te-IN")
    if stack.llm.provider != "sarvam":
        raise RuntimeError("Current Standard LLM is not Sarvam; refusing to silently substitute")
    async with connection.get_session_factory()() as db:
        tiers = (await db.scalars(select(TierAssignment))).all()
        rates = (await db.scalars(select(BillingRateVersion))).all()
        configs = (await db.scalars(select(ConfigVersion).where(ConfigVersion.resource_type.in_(
            ("platform_languages", "voice_stack", "provider_registry"))))).all()
        snapshots = [(type(row), {c.key: getattr(row, c.key) for c in row.__table__.columns})
                     for row in [*tiers, *rates, *configs]]
    resume = os.getenv("AUDIT_RESUME") == "1"
    previous = json.loads((OUT / "manifest.json").read_text(encoding="utf-8")) if resume else None
    schema = previous["schema"] if previous else "audit_telugu_" + uuid.uuid4().hex
    if not __import__("re").fullmatch(r"audit_telugu_[0-9a-f]{32}", schema):
        raise RuntimeError("Invalid owned audit schema")
    admin_engine = connection.get_engine()
    async with admin_engine.begin() as db:
        if resume:
            if not await db.scalar(text("SELECT 1 FROM pg_namespace WHERE nspname=:name"), {"name": schema}):
                raise RuntimeError("Owned audit schema no longer exists")
        else:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(connection._to_async_url(settings.database_url), pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}}, pool_size=8, max_overflow=4)
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
    await admin_engine.dispose()
    data = OUT / "isolated-data" / schema
    data.mkdir(parents=True, exist_ok=True)
    for filename in ("saas_universal_phone_stack.json", "platform_languages.json", "provider_voice_inventory.json"):
        source = original_data / filename
        if source.is_file():
            shutil.copy2(source, data / filename)
    settings.data_dir = str(data)
    os.environ["DATA_DIR"] = str(data)
    from server.call import redis_memory_cache
    redis_memory_cache._PREFIX = schema + ":memory:"
    # Storage and speech-transcription boundaries are excluded from this text-only audit.
    from server.services.r2_storage import r2_storage
    r2_storage.is_configured = lambda: False
    import server.call.post_call_transcription as transcription
    transcription.schedule_post_call_transcription = lambda _call: None
    logging.getLogger().setLevel(logging.ERROR)
    for name in ("httpx", "httpcore", "google_genai", "server"):
        logging.getLogger(name).setLevel(logging.ERROR)
    from server.utils.logger import logger, RedactingFormatter
    logger.handlers.clear()
    handler = logging.FileHandler(OUT / "runtime.log", encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    from server.providers.sarvam_llm import SarvamLLMAdapter
    original_body = SarvamLLMAdapter._request_body
    def observed_body(self, **kwargs):
        body = original_body(self, **kwargs)
        REQUESTS.append({"case": CASE.get(), "actor": ACTOR.get(), "index": len(REQUESTS), "body": body})
        return body
    SarvamLLMAdapter._request_body = observed_body
    import httpx
    original_send = httpx.AsyncClient.send
    async def guarded_send(self, request, *args, **kwargs):
        host = request.url.host
        local = isinstance(getattr(self, "_transport", None), httpx.ASGITransport)
        if not local and host not in {"api.sarvam.ai", "api.openai.com"} and not host.endswith(".googleapis.com"):
            raise RuntimeError("Audit blocked a non-inference external network request")
        event = {"case": CASE.get(), "actor": ACTOR.get(), "host": host,
                 "method": request.method, "path": request.url.path}
        NETWORK.append(event)
        try:
            response = await original_send(self, request, *args, **kwargs)
            event["status"] = response.status_code
            return response
        except Exception as exc:
            event["error"] = type(exc).__name__
            raise
    httpx.AsyncClient.send = guarded_send
    manifest = {"schema": schema, "stack": stack.to_safe_dict(), "memory_enabled": settings.working_memory_enabled,
        "memory_fallback": settings.memory_extraction_fallback, "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty_files": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
        "source_hashes": source_manifest(), "external_boundaries": ["TTS", "STT", "carrier", "integration transport", "R2"],
        "schema_retained_for_review": True}
    if previous:
        write("attempts/manifest-before-resume-" + uuid.uuid4().hex[:8] + ".json", previous)
    write("manifest.json", manifest)
    return settings, stack, manifest
