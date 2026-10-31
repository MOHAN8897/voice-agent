"""Signed portal credentials for HTTP tests that exercise authorized workflows."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth.session import create_session_token


def authenticated_dev_client(app: FastAPI) -> TestClient:
    client = TestClient(app)
    client.cookies.set("dev_session", create_session_token("dev", "synthetic-test-developer", None, "developer"))
    client.cookies.set("dev_csrf", "synthetic-test-csrf")
    client.headers["X-CSRF-Token"] = "synthetic-test-csrf"
    return client
