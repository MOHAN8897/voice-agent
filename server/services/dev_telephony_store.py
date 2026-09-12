"""Persist dev PSTN test history and dial contacts — survives server restart."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from server.config.env import get_settings


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pipeline_label(stack_override: dict[str, Any] | None) -> str:
    if isinstance(stack_override, dict) and stack_override.get("pipeline") == "realtime_voice":
        return "realtime_voice"
    return "realtime_text"


class DevTelephonyStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"history": [], "contacts": []}
        self._load()

    def _path(self):
        return get_settings().data_path / "dev_telephony.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {
                    "history": list(raw.get("history") or []),
                    "contacts": list(raw.get("contacts") or []),
                }
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "history": [dict(r) for r in self._data.get("history") or []],
                "contacts": [dict(c) for c in self._data.get("contacts") or []],
            }

    def merge_snapshot(self, snap: dict[str, Any]) -> None:
        with self._lock:
            if not self._data.get("history") and snap.get("history"):
                self._data["history"] = list(snap.get("history") or [])
            if not self._data.get("contacts") and snap.get("contacts"):
                self._data["contacts"] = list(snap.get("contacts") or [])
            if snap.get("history") or snap.get("contacts"):
                self._save()

    def reset_for_tests(self) -> None:
        with self._lock:
            self._data = {"history": [], "contacts": []}
            path = self._path()
            if path.exists():
                path.unlink(missing_ok=True)

    def record_dial(
        self,
        *,
        provider: str,
        external_id: str,
        agent_id: str,
        source_session_id: str | None,
        from_e164: str | None,
        to_e164: str | None,
        stack_override: dict[str, Any] | None,
        language: str | None,
        tier: str | None,
    ) -> dict[str, Any]:
        now = _utcnow()
        entry = {
            "history_id": uuid.uuid4().hex,
            "provider": provider,
            "external_id": external_id,
            "internal_call_id": None,
            "agent_id": agent_id,
            "source_session_id": source_session_id,
            "from_e164": from_e164,
            "to_e164": to_e164,
            "pipeline": _pipeline_label(stack_override),
            "language": language,
            "tier": tier,
            "direction": "outbound",
            "status": "placed",
            "placed_at": now,
            "answered_at": None,
            "ended_at": None,
            "duration_sec": None,
            "events": [{"at": now, "stage": "placed", "detail": "Outbound dial initiated"}],
            "usage": {},
            "cost": {},
            "meta": {"stack_override": stack_override or {}},
        }
        with self._lock:
            self._data.setdefault("history", []).insert(0, entry)
            self._data["history"] = self._data["history"][:500]
            self._save()
        return dict(entry)

    def _find_by_external(self, external_id: str) -> dict[str, Any] | None:
        for row in self._data.get("history") or []:
            if str(row.get("external_id") or "") == external_id:
                return row
        return None

    def _find_by_internal(self, internal_call_id: str) -> dict[str, Any] | None:
        for row in self._data.get("history") or []:
            if str(row.get("internal_call_id") or "") == internal_call_id:
                return row
        return None

    def _append_event(self, row: dict[str, Any], stage: str, detail: str = "") -> None:
        events = row.setdefault("events", [])
        if events and events[-1].get("stage") == stage:
            return
        events.append({"at": _utcnow(), "stage": stage, "detail": detail})

    def sync_registry_row(self, row: dict[str, Any], *, provider: str) -> None:
        external_id = str(
            row.get("call_control_id") or row.get("call_sid") or row.get("call_uuid") or ""
        )
        if not external_id:
            return
        status = str(row.get("status") or "").lower()
        internal = str(row.get("internal_call_id") or "") or None
        with self._lock:
            entry = self._find_by_external(external_id)
            if entry is None:
                return
            changed = False
            if internal and not entry.get("internal_call_id"):
                entry["internal_call_id"] = internal
                self._append_event(entry, "answered", "Media stream connected")
                entry["answered_at"] = entry.get("answered_at") or _utcnow()
                entry["status"] = "ongoing"
                changed = True
            if status in {"ringing", "initiated"} and entry.get("status") == "placed":
                entry["status"] = "ringing"
                self._append_event(entry, "ringing", f"Provider status: {status}")
                changed = True
            if status in {"streaming", "in-progress", "active"} and entry.get("status") in {
                "placed",
                "ringing",
            }:
                entry["status"] = "ongoing"
                entry["answered_at"] = entry.get("answered_at") or _utcnow()
                self._append_event(entry, "ongoing", "Call in progress")
                changed = True
            if status in {"completed", "failed", "busy", "no-answer", "canceled", "hangup"}:
                if entry.get("status") != "ended":
                    entry["status"] = "ended"
                    entry["ended_at"] = _utcnow()
                    self._append_event(entry, "hangup", f"Provider status: {status}")
                    changed = True
            if changed:
                self._finalize_costs(entry)
                self._save()

    def _finalize_costs(self, entry: dict[str, Any]) -> bool:
        cid = str(entry.get("internal_call_id") or "")
        if not cid:
            return False
        from server.call.call_ledger import call_ledger

        review = call_ledger.review_fields(cid)
        meta = call_ledger.read_meta(cid)
        usage = review.get("usage") if isinstance(review.get("usage"), dict) else {}
        duration = review.get("duration_sec") or meta.get("duration_sec")
        cost = {
            "cost_usd": review.get("cost_usd"),
            "cost_inr": review.get("cost_inr"),
            "cost_inr_per_min": review.get("cost_inr_per_min"),
            "model_cost_usd": review.get("model_cost_usd"),
            "model_cost_inr": review.get("model_cost_inr"),
            "telnyx_usd": review.get("telnyx_usd"),
            "telnyx_inr": review.get("telnyx_inr"),
            "pipeline": review.get("pipeline") or entry.get("pipeline"),
            "end_reason": review.get("end_reason") or meta.get("end_reason"),
        }
        changed = False
        if usage and entry.get("usage") != usage:
            entry["usage"] = usage
            changed = True
        if duration is not None and entry.get("duration_sec") != duration:
            entry["duration_sec"] = duration
            changed = True
        if any(v is not None for v in cost.values()) and entry.get("cost") != cost:
            entry["cost"] = cost
            changed = True
        if review.get("pipeline") and entry.get("pipeline") != review.get("pipeline"):
            entry["pipeline"] = review.get("pipeline")
            changed = True
        return changed

    def list_history(
        self,
        *,
        agent_id: str | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            rows = list(self._data.get("history") or [])
            if agent_id:
                rows = [r for r in rows if str(r.get("agent_id") or "") == agent_id]
            total = len(rows)
            page = rows[offset : offset + max(1, min(limit, 50))]
            dirty = False
            for row in page:
                if self._finalize_costs(row):
                    dirty = True
            if dirty:
                self._save()
            return [dict(r) for r in page], total

    def get_history(self, history_id: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._data.get("history") or []:
                if str(row.get("history_id") or "") == history_id:
                    if self._finalize_costs(row):
                        self._save()
                    return dict(row)
        return None

    def list_contacts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(c) for c in self._data.get("contacts") or []]

    def upsert_contact(
        self,
        *,
        name: str,
        phone: str,
        notes: str = "",
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        phone_clean = phone.strip()
        name_clean = name.strip()
        if not phone_clean:
            raise ValueError("phone required")
        with self._lock:
            contacts = self._data.setdefault("contacts", [])
            if contact_id:
                for item in contacts:
                    if str(item.get("contact_id") or "") == contact_id:
                        item["name"] = name_clean
                        item["phone"] = phone_clean
                        item["notes"] = notes.strip()
                        item["updated_at"] = _utcnow()
                        self._save()
                        return dict(item)
                raise KeyError("contact not found")
            entry = {
                "contact_id": uuid.uuid4().hex,
                "name": name_clean,
                "phone": phone_clean,
                "notes": notes.strip(),
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
            }
            contacts.insert(0, entry)
            self._save()
            return dict(entry)

    def delete_contact(self, contact_id: str) -> bool:
        with self._lock:
            contacts = self._data.setdefault("contacts", [])
            before = len(contacts)
            self._data["contacts"] = [
                c for c in contacts if str(c.get("contact_id") or "") != contact_id
            ]
            if len(self._data["contacts"]) == before:
                return False
            self._save()
            return True


dev_telephony_store = DevTelephonyStore()
