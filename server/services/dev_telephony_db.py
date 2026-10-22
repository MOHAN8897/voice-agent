"""Optional Postgres mirror for dev PSTN test history and contacts."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import String, Text, delete, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column

from server.db.connection import get_session_factory
from server.db.models.entities import Base
from server.utils.logger import logger


class DevPstnHistoryRow(Base):
    __tablename__ = "dev_pstn_history"

    history_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    internal_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    placed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class DevPstnContactRow(Base):
    __tablename__ = "dev_pstn_contacts"

    contact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


async def mirror_store_snapshot(data: dict[str, Any]) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    history = list(data.get("history") or [])
    contacts = list(data.get("contacts") or [])
    try:
        async with factory() as session:
            if history:
                for row in history:
                    hid = str(row.get("history_id") or "")
                    if not hid:
                        continue
                    stmt = insert(DevPstnHistoryRow).values(
                        history_id=hid,
                        agent_id=str(row.get("agent_id") or "") or None,
                        external_id=str(row.get("external_id") or "") or None,
                        internal_call_id=str(row.get("internal_call_id") or "") or None,
                        placed_at=str(row.get("placed_at") or "") or None,
                        payload=dict(row),
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[DevPstnHistoryRow.history_id],
                        set_={
                            "agent_id": stmt.excluded.agent_id,
                            "external_id": stmt.excluded.external_id,
                            "internal_call_id": stmt.excluded.internal_call_id,
                            "placed_at": stmt.excluded.placed_at,
                            "payload": stmt.excluded.payload,
                        },
                    )
                    await session.execute(stmt)
            if contacts is not None:
                await session.execute(delete(DevPstnContactRow))
                for contact in contacts:
                    cid = str(contact.get("contact_id") or "")
                    if not cid:
                        continue
                    session.add(
                        DevPstnContactRow(
                            contact_id=cid,
                            name=str(contact.get("name") or ""),
                            phone=str(contact.get("phone") or ""),
                            notes=str(contact.get("notes") or ""),
                            payload=dict(contact),
                        )
                    )
            await session.commit()
    except Exception as exc:
        logger.warning("[DEV_TELEPHONY] db mirror failed: %s", str(exc)[:200])


async def load_snapshot_from_db() -> dict[str, Any] | None:
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        async with factory() as session:
            hist_result = await session.execute(
                select(DevPstnHistoryRow).order_by(DevPstnHistoryRow.placed_at.desc())
            )
            contact_result = await session.execute(select(DevPstnContactRow))
            history = [dict(row.payload) for row in hist_result.scalars().all()]
            contacts = [dict(row.payload) for row in contact_result.scalars().all()]
            if not history and not contacts:
                return None
            return {"history": history, "contacts": contacts}
    except Exception as exc:
        logger.warning("[DEV_TELEPHONY] db load failed: %s", str(exc)[:200])
        return None
