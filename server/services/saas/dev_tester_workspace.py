"""Dev testers see the platform default workspace for agents & phone lines (not dev stack UI)."""
from __future__ import annotations

import uuid

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.services.saas.platform_admins import is_dev_tester_email
from sqlalchemy import select


def workspace_tenant_id_for_subscriber(tenant_id: uuid.UUID, email: str | None) -> uuid.UUID:
    """Agents and phone lines resolve on the shared platform tenant for dev testers."""
    if not is_dev_tester_email(email):
        return tenant_id
    settings = get_settings()
    try:
        return uuid.UUID(str(settings.default_tenant_id))
    except (ValueError, TypeError):
        return tenant_id


async def ensure_dev_tester_phone_line(tenant_id: uuid.UUID, email: str | None) -> None:
    """Ensure TELNYX_PHONE_NUMBER exists as a PhoneNumber row on the workspace tenant."""
    if not is_dev_tester_email(email):
        return
    settings = get_settings()
    e164 = (settings.telnyx_phone_number or "").strip()
    if not e164:
        return
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        existing = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.e164 == e164,
                PhoneNumber.released_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            return
        session.add(
            PhoneNumber(
                tenant_id=tenant_id,
                e164=e164,
                status="active",
                inbound_enabled=True,
                outbound_enabled=True,
                billing_source="platform",
            )
        )
        await session.commit()
