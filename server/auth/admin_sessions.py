"""Revocation state for dev-portal sessions held by stored platform-admin accounts.

Dev-portal session cookies are stateless HMAC tokens, so on their own they cannot
be revoked: a suspended admin, a demoted admin or a "sign out everywhere" would
keep working until the 7-day expiry. Tokens issued to stored accounts therefore
carry a reference (`a:<account_id>:<epoch>`), and every parse checks it against
this in-memory snapshot of the accounts table:

* the account must exist and be `active`,
* the token's epoch must equal the account's current `session_epoch` (bumped on
  sign-out-everywhere, suspension, password reset and removal),
* the role used for authorization is the account's *current* role, not the one
  baked into the cookie at sign-in.

The snapshot is tiny (one row per admin) and is refreshed from the database by
the async dev-session dependency whenever it is older than `_MAX_AGE_SEC`, and
immediately after any admin-management change in this process. Sync call sites
that parse cookies directly use the last snapshot. When no snapshot has ever
loaded, account tokens are refused (fail closed); the env-configured built-in
login does not depend on this module.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_AGE_SEC = 10.0


@dataclass(frozen=True)
class AccountSessionState:
    account_id: str
    username: str
    role: str
    status: str
    session_epoch: int


_snapshot: dict[str, AccountSessionState] | None = None
_loaded_at: float = 0.0
_lock = asyncio.Lock()


def account_ref(account_id: uuid.UUID | str, epoch: int) -> str:
    return f"a:{account_id}:{int(epoch)}"


def parse_account_ref(ref: str | None) -> tuple[str, int] | None:
    if not ref or not ref.startswith("a:"):
        return None
    parts = ref.split(":")
    if len(parts) != 3:
        return None
    try:
        return str(uuid.UUID(parts[1])), int(parts[2])
    except (ValueError, TypeError):
        return None


def resolve_account_ref(ref: str) -> AccountSessionState | None:
    """The live account behind a session reference, or None when it is no longer valid."""
    parsed = parse_account_ref(ref)
    if parsed is None or _snapshot is None:
        return None
    account_id, epoch = parsed
    state = _snapshot.get(account_id)
    if state is None or state.status != "active" or state.session_epoch != epoch:
        return None
    return state


def set_snapshot(states: list[AccountSessionState]) -> None:
    global _snapshot, _loaded_at
    _snapshot = {s.account_id: s for s in states}
    _loaded_at = time.monotonic()


def clear_snapshot_for_tests() -> None:
    global _snapshot, _loaded_at
    _snapshot = None
    _loaded_at = 0.0


async def refresh(force: bool = False) -> None:
    """Reload the snapshot when stale. Never raises."""
    if not force and _snapshot is not None and time.monotonic() - _loaded_at < _MAX_AGE_SEC:
        return
    async with _lock:
        if not force and _snapshot is not None and time.monotonic() - _loaded_at < _MAX_AGE_SEC:
            return
        try:
            from server.services.saas.admin_accounts import load_session_states

            states = await load_session_states()
        except Exception as exc:  # DB down or table missing: keep what we had.
            logger.warning("Admin session snapshot refresh failed: %s", exc)
            return
        if states is None:
            # No database configured: there can be no stored accounts.
            set_snapshot([])
            return
        set_snapshot(states)
