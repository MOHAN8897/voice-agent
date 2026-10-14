"""Dev testers see the platform default workspace for agents & phone lines (not dev stack UI)."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.services.saas.platform_admins import is_dev_tester_email

logger = logging.getLogger(__name__)


def workspace_tenant_id_for_subscriber(tenant_id: uuid.UUID, email: str | None) -> uuid.UUID:
    """Agents and phone lines resolve on the subscriber's workspace tenant.

    Falls back to the platform default tenant only when the subscriber has no tenant assigned
    or is explicitly operating on the platform default.
    """
    settings = get_settings()
    default_tid = None
    try:
        default_tid = uuid.UUID(str(settings.default_tenant_id))
    except (ValueError, TypeError):
        pass

    if tenant_id and (default_tid is None or tenant_id != default_tid):
        return tenant_id
    if not is_dev_tester_email(email):
        return tenant_id
    return default_tid or tenant_id


async def ensure_dev_tester_phone_line(tenant_id: uuid.UUID, email: str | None) -> None:
    """Ensure TELNYX_PHONE_NUMBER exists as a PhoneNumber row on the workspace tenant.

    Never raises into the list endpoint: e164 is globally unique, so a release +
    re-ensure or a row on another tenant must be re-homed, not force-inserted.
    """
    if not is_dev_tester_email(email):
        return
    settings = get_settings()
    try:
        default_tid = uuid.UUID(str(settings.default_tenant_id))
    except (ValueError, TypeError):
        default_tid = None
    if default_tid and tenant_id != default_tid:
        return
    factory = get_session_factory()
    if factory is None:
        return

    active_prov = "vobiz"
    try:
        from server.services.telephony import active_telephony_provider
        active_prov = active_telephony_provider()
    except Exception:
        pass

    candidates: list[tuple[str, str]] = []
    if active_prov == "vobiz":
        vobiz_num = (getattr(settings, "vobiz_phone_number", None) or "+917965480745").strip()
        if vobiz_num:
            candidates.append((vobiz_num, "vobiz"))
    elif active_prov == "telnyx":
        telnyx_num = (settings.telnyx_phone_number or "+13526146416").strip()
        if telnyx_num:
            candidates.append((telnyx_num, "telnyx"))

    for e164, prov in candidates:
        try:
            async with factory() as session:
                result = await session.execute(select(PhoneNumber).where(PhoneNumber.e164 == e164))
                row = result.scalar_one_or_none()
                if row is not None:
                    changed = False
                    if row.tenant_id != tenant_id:
                        row.tenant_id = tenant_id
                        changed = True
                    if row.released_at is not None:
                        row.released_at = None
                        changed = True
                    if row.status not in ("active", "pending"):
                        row.status = "active"
                        changed = True
                    if not row.inbound_enabled:
                        row.inbound_enabled = True
                        changed = True
                    if not row.outbound_enabled:
                        row.outbound_enabled = True
                        changed = True
                    if prov == "vobiz" and not getattr(row, "carrier_number_id", None):
                        row.carrier_number_id = "18d1efff-6654-4b22-b650-ccda743b1789"
                        changed = True
                    if changed:
                        await session.commit()
                    continue

                session.add(
                    PhoneNumber(
                        tenant_id=tenant_id,
                        e164=e164,
                        status="active",
                        inbound_enabled=True,
                        outbound_enabled=True,
                        billing_source="platform",
                        carrier_number_id="18d1efff-6654-4b22-b650-ccda743b1789" if prov == "vobiz" else None,
                        telnyx_number_id="carrier_platform" if prov == "telnyx" else None,
                    )
                )
                await session.commit()
        except IntegrityError:
            logger.info("dev_tester_phone_line.race provider=%s", prov)
        except Exception as exc:
            logger.warning(
                "dev_tester_phone_line.failed provider=%s error=%s",
                prov,
                type(exc).__name__,
            )
