"""Portal password verification — plain env or PBKDF2 hash (pbkdf2-sha256$iter$salt$hash)."""
from __future__ import annotations

import hashlib
import hmac


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
        derived = hashlib.pbkdf2_hmac("sha256", provided.encode(), salt, iterations)
        return hmac.compare_digest(derived, expected)
    return hmac.compare_digest(stored, provided)


def hash_portal_password(password: str, iterations: int = 120000) -> str:
    salt = hashlib.sha256(password.encode()).digest()[:16]
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2-sha256${iterations}${salt.hex()}${derived.hex()}"
