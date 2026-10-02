"""The request currently being handled, available to anything that needs it.

Logging needs the caller's IP and user agent, but threading a `Request` through
19 admin call sites to reach the recorder is a large, easy-to-miss diff — and the
next call site added later would simply forget.

A middleware puts the request in a context variable instead, so any code running
inside the request can read it without being handed anything. This is exactly
what context variables are for: per-task state that must not leak between
concurrent requests.
"""
from __future__ import annotations

import contextvars
from typing import Any

_current_request: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "voxly_current_request", default=None
)


def set_current_request(request: Any) -> contextvars.Token:
    return _current_request.set(request)


def reset_current_request(token: contextvars.Token) -> None:
    _current_request.reset(token)


def get_current_request() -> Any:
    """The in-flight request, or None outside a request (workers, scripts)."""
    return _current_request.get()


def request_context() -> dict[str, str | None]:
    """IP, user agent and request id for the in-flight request, if any."""
    request = _current_request.get()
    if request is None:
        return {"ip": None, "user_agent": None, "request_id": None}
    try:
        headers = getattr(request, "headers", None)
        return {
            "ip": getattr(getattr(request, "client", None), "host", None),
            "user_agent": headers.get("user-agent") if headers is not None else None,
            "request_id": headers.get("x-request-id") if headers is not None else None,
        }
    except Exception:
        # Request introspection is a nicety; it must never break a log write.
        return {"ip": None, "user_agent": None, "request_id": None}