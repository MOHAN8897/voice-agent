"""Portal password verification — plain env or PBKDF2 hash (pbkdf2-sha256$iter$salt$hash)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

DEFAULT_PBKDF2_ITERATIONS = 600000


def verify_portal_password(stored: str | None, provided: str) -> bool:
    if not stored or not provided:
        return False
    if stored.startswith("pbkdf2-sha256$"):
        parts = stored.split("$")
        if len(parts) != 4:
            return False
        try:
            iterations = int(parts[1])
            salt = bytes.fromhex(parts[2])
            expected = bytes.fromhex(parts[3])
        except (ValueError, TypeError):
            return False
        if not 1 <= iterations <= 10000000 or not 8 <= len(salt) <= 64 or len(expected) != 32:
            return False
        derived = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, iterations)
        return hmac.compare_digest(derived, expected)
    return hmac.compare_digest(stored.encode("utf-8"), provided.encode("utf-8"))


def hash_portal_password(password: str, iterations: int = DEFAULT_PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2-sha256${iterations}${salt.hex()}${derived.hex()}"


def password_hash_needs_upgrade(stored: str) -> bool:
    try:
        return not stored.startswith("pbkdf2-sha256$") or int(stored.split("$")[1]) < DEFAULT_PBKDF2_ITERATIONS
    except (ValueError, IndexError):
        return True
