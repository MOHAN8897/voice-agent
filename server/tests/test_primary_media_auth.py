import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services import vobiz_client as module
from server.routes import vobiz_ws as route


class SharedRedis:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()
    def get(self, key):
        with self.lock: return self.values.get(key)
    def set(self, key, value, nx=False, **_kw):
        with self.lock:
            if nx and key in self.values: return False
            self.values[key] = value
            return True
    def getdel(self, key):
        with self.lock: return self.values.pop(key, None)


def test_shared_media_token_consumed_once_even_after_callback_update(monkeypatch):
    shared = SharedRedis()
    stores = [module.VobizStreamTokens() for _ in range(10)]
    for store in stores:
        monkeypatch.setattr(store, "_redis", lambda: shared)
    token = stores[0].create(call_uuid="isolated-call", agent_id="isolated-agent")
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda store: store.consume(token), stores))
    assert sum(value is not None for value in results) == 1
    stores[0].put(token, call_uuid="isolated-call", agent_id="isolated-agent")
    assert all(store.consume(token) is None for store in stores)


def test_local_token_not_resurrected_and_shared_failure_closed(monkeypatch):
    store = module.VobizStreamTokens()
    monkeypatch.setattr(store, "_redis", lambda: None)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(app_environment="development"))
    token = store.create(call_uuid="isolated")
    assert store.consume(token)
    store.put(token, call_uuid="isolated")
    assert store.consume(token) is None
    token = store.create(call_uuid="other-isolated")
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(app_environment="production"))
    assert store.consume(token) is None
    with pytest.raises(module.VobizConfigError):
        store.create(call_uuid="blocked")


async def test_media_socket_claims_before_start_and_rejects_replay(monkeypatch):
    store = module.VobizStreamTokens()
    monkeypatch.setattr(store, "_redis", lambda: None)
    monkeypatch.setattr(store, "_shared_required", lambda: False)
    monkeypatch.setattr(route, "vobiz_stream_tokens", store)
    registry = SimpleNamespace(get=lambda _key: {}, atomic_check_and_set=AsyncMock(return_value=True))
    monkeypatch.setattr(route, "vobiz_call_registry", registry)
    started = []
    class Bridge:
        ws_id = "isolated"
        def __init__(self, ws): self.ws = ws
        async def run(self, **kw):
            started.append(kw)
    monkeypatch.setattr(route, "VobizPstnBridge", Bridge)
    token = store.create(call_uuid="isolated", agent_id="agent")
    def socket():
        return SimpleNamespace(query_params={"token": token, "call_uuid": "isolated"}, accept=AsyncMock(), close=AsyncMock())
    first, replay = socket(), socket()
    await route.vobiz_stream_ws(first)
    await route.vobiz_stream_ws(replay)
    first.accept.assert_awaited_once()
    replay.accept.assert_not_awaited()
    replay.close.assert_awaited_once()
    assert len(started) == 1


async def test_distributed_call_claim_allows_only_one_worker(monkeypatch):
    shared = SharedRedis()
    registries = [module.VobizCallRegistry() for _ in range(8)]
    for registry in registries:
        monkeypatch.setattr(registry, "_redis", lambda: shared)
        monkeypatch.setattr(registry, "upsert", lambda *_: {})
    results = await asyncio.gather(*(registry.atomic_check_and_set("isolated", "stream") for registry in registries))
    assert sum(results) == 1


def test_registry_cache_is_bounded_and_alias_cycles_fail_closed(monkeypatch):
    import time
    registry = module.VobizCallRegistry()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(app_environment="development"))
    registry._max_local_calls = 10
    for n in range(30):
        registry.upsert(f"isolated-{n}", {"status": "ended", "token": "private", "stream_url": "private"})
    assert len(registry._calls) == 10
    assert all("token" not in row and "stream_url" not in row for row in registry.list_recent())
    registry.upsert("a", {"aliased_to": "b"})
    registry.upsert("b", {"aliased_to": "a"})
    assert registry.get("a") is None


def test_real_redis_keeps_multiworker_metadata_and_single_use_tokens(monkeypatch):
    import os, uuid
    from urllib.parse import urlsplit
    url = os.environ.get("CAMPAIGN_AUDIT_REDIS_URL")
    if not url:
        pytest.skip("Run with the owned Redis audit container")
    assert (urlsplit(url).hostname, urlsplit(url).port) == ("127.0.0.1", 56379)
    import redis
    client = redis.Redis.from_url(url, decode_responses=True)
    prefix = "audit:" + uuid.uuid4().hex + ":"
    stores = [module.VobizStreamTokens() for _ in range(8)]
    registries = [module.VobizCallRegistry() for _ in range(4)]
    for store in stores:
        monkeypatch.setattr(store, "_redis", lambda: client)
        store._REDIS_PREFIX = prefix + "token:"
    for registry in registries:
        monkeypatch.setattr(registry, "_redis", lambda: client)
        registry._REDIS_PREFIX = prefix + "call:"
        registry._REDIS_RECENT_KEY = prefix + "recent"
    try:
        token = stores[0].create(call_uuid="isolated")
        assert len(stores[0]._tokens) == 0  # shared mode avoids a second unbounded token cache
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda store: store.consume(token), stores))
        assert sum(value is not None for value in responses) == 1
        stores[0].put(token, call_uuid="isolated")
        assert stores[1].consume(token) is None
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: registries[i % 4].upsert("isolated", {f"field_{i}": i}), range(16)))
        value = registries[0].get("isolated")
        assert all(value[f"field_{i}"] == i for i in range(16))
        registries[1].upsert("isolated", {"ended": True})
        assert registries[0].get("isolated")["ended"] is True
        assert registries[0].list_recent()[0]["ended"] is True
    finally:
        keys = list(client.scan_iter(match=prefix + "*"))
        assert all(key.startswith(prefix) for key in keys)
        if keys: client.delete(*keys)


async def test_tenant_provider_status_does_not_expose_platform_phone(monkeypatch):
    from server.routes.app_telephony import telephony_provider_info
    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr("server.services.saas.platform_admins.is_platform_admin_email", lambda _email: False)
    monkeypatch.setattr("server.services.telephony_status.all_provider_status", AsyncMock(return_value=[{"id": "vobiz", "phone_number": "+12025550199", "enabled": True, "ready": True}]))
    result = await telephony_provider_info(SimpleNamespace(email="tenant@example.invalid"))
    assert result["phoneNumber"] is None and result["providers"][0]["phoneNumber"] is None
    assert "vobiz" not in str(result).lower()
