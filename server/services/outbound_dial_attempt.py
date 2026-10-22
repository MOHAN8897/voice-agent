"""Durable request-scoped dial idempotency. Never expire an uncertain carrier call.

Redis is the shared authority when configured. Without Redis, SQLite provides
atomic claims across workers on this host. Store failures fail closed: a call
must never be placed when its request claim cannot be recorded.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

class AttemptStoreUnavailable(RuntimeError):
    pass

class AttemptConflict(ValueError):
    pass

def _redis():
    from server.call.redis_memory_cache import _redis as get_redis
    return get_redis()

def _key(request_id: str, scope: str = '') -> str:
    return 'voice:outbound:dial_attempt:v2:' + hashlib.sha256(f'{scope}\0{request_id}'.encode()).hexdigest()

@contextmanager
def _database():
    from server.config.env import get_settings
    path = Path(get_settings().data_dir) / 'outbound-dial-attempts.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        yield db

def get_attempt(request_id: str, *, scope: str = '') -> dict[str, Any] | None:
    key = _key(request_id, scope)
    try:
        client = _redis()
        if client is not None:
            raw = client.get(key)
        else:
            with _database() as db:
                row = db.execute('SELECT payload FROM attempts WHERE id=?', (key,)).fetchone()
                raw = row[0] if row else None
        return json.loads(raw) if raw else None
    except Exception as exc:
        raise AttemptStoreUnavailable('Dial request storage is unavailable; no new call was placed') from exc

def claim_attempt(request_id: str, *, scope: str = '', fingerprint: str = '') -> tuple[bool, dict[str, Any] | None]:
    if not request_id.strip():
        raise ValueError('A dial request ID is required for a durable claim')
    key = _key(request_id, scope)
    row = {'status': 'claimed', 'fingerprint': fingerprint, 'updated_at': time.time()}
    encoded = json.dumps(row)
    try:
        client = _redis()
        if client is not None:
            claimed = bool(client.set(key, encoded, nx=True))
        else:
            with _database() as db:
                claimed = db.execute('INSERT OR IGNORE INTO attempts(id,payload) VALUES (?,?)', (key, encoded)).rowcount == 1
        if claimed:
            return True, None
        existing = get_attempt(request_id, scope=scope)
        if existing is None:
            raise AttemptStoreUnavailable('Existing dial claim could not be read')
        if existing.get('fingerprint', '') != fingerprint:
            raise AttemptConflict('This dial request ID was already used for different call settings')
        return False, existing
    except (AttemptConflict, AttemptStoreUnavailable):
        raise
    except Exception as exc:
        raise AttemptStoreUnavailable('Unable to claim dial request; no new call was placed') from exc

def save_attempt(request_id: str, payload: dict[str, Any], *, scope: str = '') -> None:
    existing = get_attempt(request_id, scope=scope)
    if existing is None:
        raise AttemptStoreUnavailable('Cannot finish a dial request without its original claim')
    row = {**existing, **payload, 'updated_at': time.time()}
    try:
        client = _redis()
        if client is not None:
            client.set(_key(request_id, scope), json.dumps(row))
        else:
            with _database() as db:
                db.execute('UPDATE attempts SET payload=? WHERE id=?', (json.dumps(row), _key(request_id, scope)))
    except Exception as exc:
        raise AttemptStoreUnavailable('Carrier result could not be persisted; reconcile this request before retrying') from exc

async def execute_dial_attempt(*, request_id: str | None, scope: str, payload: dict, operation):
    """Replay completed results; keep pending/uncertain attempts closed to redial."""
    # Legacy clients without IDs still get one carrier attempt; current UIs send IDs.
    if not request_id:
        return await operation()
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    try:
        claimed, row = claim_attempt(request_id, scope=scope, fingerprint=fingerprint)
        if not claimed:
            if row.get('response') is not None:
                return dict(row['response'])
            return {'ok': False, 'code': 'dial_pending', 'dialRequestId': request_id,
                    'error': 'This call request is pending or uncertain. Reconcile the existing call; do not redial.'}
    except (AttemptConflict, AttemptStoreUnavailable) as exc:
        return {'ok': False, 'code': 'dial_request_conflict' if isinstance(exc, AttemptConflict) else 'dial_store_unavailable', 'error': str(exc)}
    try:
        result = await operation()
        save_attempt(request_id, {'status': 'completed', 'response': result}, scope=scope)
        return result
    except BaseException:
        # A timeout/cancellation is not proof that the carrier did not dial.
        try:
            save_attempt(request_id, {'status': 'uncertain'}, scope=scope)
        except AttemptStoreUnavailable:
            pass
        raise
