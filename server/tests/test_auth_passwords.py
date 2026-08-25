"""Portal password hashing tests."""
from server.auth.passwords import hash_portal_password, verify_portal_password


def test_plain_password_verify():
    assert verify_portal_password("secret", "secret")
    assert not verify_portal_password("secret", "wrong")


def test_pbkdf2_password_verify():
    stored = hash_portal_password("devpass")
    assert stored.startswith("pbkdf2-sha256$")
    assert verify_portal_password(stored, "devpass")
    assert not verify_portal_password(stored, "nope")
