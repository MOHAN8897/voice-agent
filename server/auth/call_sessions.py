"""Verified call access and tenant-bound browser session identifiers."""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from server.auth.dependencies import require_permission
from server.auth.session import cookie_names, parse_session_token
from server.auth.subscriber_dependencies import (
    SubscriberPrincipal,
    require_subscriber_jwt_if_enabled,
)

CallPrincipal = Annotated[SubscriberPrincipal | None, Depends(require_subscriber_jwt_if_enabled)]


def resolve_call_tenant(request: Request, principal: SubscriberPrincipal | None) -> str | None:
    """None is reserved for a signed, privileged Dev Portal session."""
    if principal is not None and principal.tenant_id:
        return str(principal.tenant_id)
    names = cookie_names()
    dev = parse_session_token(request.cookies.get(names["dev"], ""), "dev")
    if dev is not None:
        require_permission(dev, "dev.platform_brain")
        return None
    app = parse_session_token(request.cookies.get(names["app"], ""), "app")
    if app is not None and app.tenant_id:
        require_permission(app, "app.test_studio")
        return str(app.tenant_id)
    raise HTTPException(status_code=401, detail="Authentication required")


def tenant_session_id(tenant_id: str, client_session: str | None) -> str:
    """Do not let a browser choose another tenant's runtime/config cache key."""
    tenant_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
    prefix = f"call-{tenant_hash}-"
    raw = client_session or uuid.uuid4().hex
    if re.fullmatch(re.escape(prefix) + r"[a-f0-9]{32}", raw):
        return raw
    return prefix + hashlib.sha256(raw.encode()).hexdigest()[:32]
