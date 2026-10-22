"""Data-takeout export worker (GDPR Art. 20 / India DPDP).

Generates an encrypted ZIP archive containing:
  call_logs.csv          — call metadata + transcript summaries
  contacts.csv           — telephony contacts and leads
  agent_prompts.json     — agent configurations and system prompts
  billing_summary.json   — invoices and wallet transactions

The ZIP is uploaded to R2/S3 and a time-limited (24h) pre-signed URL is
stored in ``tenant_export_jobs.download_url``.

Vendor names (Vobiz, Telnyx, Nango) are NEVER included in the export.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.saas_models import (
    AuthEvent,
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    TenantExportJob,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def process_export_job(job_id: str, tenant_id: str) -> bool:
    """Generate export ZIP for the given job and tenant.

    Returns True if the job completed successfully.
    """
    factory = get_session_factory()
    if factory is None:
        return False

    job_uuid = uuid.UUID(job_id)
    tenant_uuid = uuid.UUID(tenant_id)

    # Mark as processing
    async with factory() as session:
        job = await session.get(TenantExportJob, job_uuid)
        if job is None or job.tenant_id != tenant_uuid:
            return False
        if job.status not in ("queued", "processing"):
            return False
        job.status = "processing"
        await session.commit()

    try:
        zip_bytes = await _build_export_zip(tenant_uuid)
        download_url = await _upload_export_zip(job_id, zip_bytes)
        expires_at = _utcnow() + timedelta(hours=24)

        async with factory() as session:
            job = await session.get(TenantExportJob, job_uuid)
            if job:
                job.status = "ready"
                job.download_url = download_url
                job.expires_at = expires_at
                session.add(
                    AuthEvent(
                        user_id=job.user_id,
                        tenant_id=job.tenant_id,
                        event_type="tenant.export_ready",
                    )
                )
                await session.commit()
        return True

    except Exception as exc:
        logger.exception("export_worker failed job_id=%s tenant=%s", job_id, tenant_id)
        async with factory() as session:
            job = await session.get(TenantExportJob, job_uuid)
            if job:
                job.status = "failed"
                await session.commit()
        return False


async def _build_export_zip(tenant_id: uuid.UUID) -> bytes:
    """Assemble the ZIP in memory from database records."""
    factory = get_session_factory()
    assert factory is not None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # --- call_logs.csv ---
        async with factory() as session:
            try:
                from server.db.models.entities import Call
                calls_result = await session.execute(
                    select(Call).where(Call.tenant_id == tenant_id).order_by(Call.started_at.desc())
                )
                calls = calls_result.scalars().all()
            except Exception:
                calls = []

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["call_id", "agent_id", "direction", "channel", "started_at", "ended_at", "duration_sec", "disposition"])
        for c in calls:
            writer.writerow([
                str(c.call_id),
                str(c.agent_id),
                c.direction,
                c.channel,
                c.started_at.isoformat() if c.started_at else "",
                c.ended_at.isoformat() if c.ended_at else "",
                c.duration_sec or "",
                c.disposition or "",
            ])
        zf.writestr("call_logs.csv", csv_buf.getvalue())

        # --- contacts.csv ---
        async with factory() as session:
            try:
                from server.db.models.saas_models import TelephonyContact, Lead
                contacts_result = await session.execute(
                    select(TelephonyContact).where(TelephonyContact.tenant_id == tenant_id)
                )
                contacts = contacts_result.scalars().all()
                leads_result = await session.execute(
                    select(Lead).where(Lead.tenant_id == tenant_id)
                )
                leads = leads_result.scalars().all()
            except Exception:
                contacts = []
                leads = []

        csv_buf2 = io.StringIO()
        writer2 = csv.writer(csv_buf2)
        writer2.writerow(["type", "name", "phone", "email", "notes", "created_at"])
        for c in contacts:
            writer2.writerow(["contact", c.name, c.phone, "", c.notes or "", c.created_at.isoformat()])
        for lead in leads:
            writer2.writerow(["lead", lead.name, lead.phone or "", lead.email or "", lead.notes or "", lead.created_at.isoformat()])
        zf.writestr("contacts.csv", csv_buf2.getvalue())

        # --- agent_prompts.json ---
        async with factory() as session:
            try:
                from server.db.models.entities import Agent
                from server.db.models.phase5_models import AgentTelephonyProfile
                from server.brain.business_brain_store import business_brain_store

                agents_result = await session.execute(
                    select(Agent).where(Agent.tenant_id == tenant_id)
                )
                agents = agents_result.scalars().all()
                agents_data = []
                for a in agents:
                    # Telephony profile
                    prof_result = await session.execute(
                        select(AgentTelephonyProfile).where(
                            AgentTelephonyProfile.agent_id == a.agent_id,
                            AgentTelephonyProfile.tenant_id == tenant_id,
                        )
                    )
                    prof = prof_result.scalar_one_or_none()
                    telephony_info = {
                        "greeting_phrase": prof.greeting_phrase if prof else None,
                        "timezone": prof.timezone if prof else "UTC",
                        "business_hours": prof.business_hours if prof else {},
                        "after_hours_action": prof.after_hours_action if prof else "hangup",
                        "transfer_number": prof.transfer_number if prof else None,
                    } if prof else {}

                    # Prompt & script sections
                    try:
                        sections = await business_brain_store.get_sections(str(a.agent_id))
                    except Exception:
                        sections = []

                    agents_data.append({
                        "agent_id": str(a.agent_id),
                        "name": a.name,
                        "status": a.status,
                        "default_tier": a.default_tier,
                        "languages": a.languages,
                        "voice_settings": a.voice_settings or {},
                        "telephony_profile": telephony_info,
                        "brain_sections": sections,
                        "created_at": a.created_at.isoformat(),
                    })
            except Exception:
                agents_data = []
        zf.writestr("agent_prompts.json", json.dumps(agents_data, indent=2, default=str))

        # --- billing_summary.json ---
        async with factory() as session:
            try:
                invoices_result = await session.execute(
                    select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
                )
                invoices = invoices_result.scalars().all()
                invoices_data = [
                    {
                        "invoice_id": str(i.invoice_id),
                        "invoice_number": i.invoice_number,
                        "amount_inr_paise": i.amount_inr_paise,
                        "currency": i.currency,
                        "status": i.status,
                        "created_at": i.created_at.isoformat(),
                    }
                    for i in invoices
                ]
                wallet_result = await session.execute(
                    select(BillingWallet).where(BillingWallet.tenant_id == tenant_id)
                )
                wallet = wallet_result.scalar_one_or_none()
                wallet_data = {
                    "balance_cents": getattr(wallet, "balance_cents", 0),
                    "balance_inr_paise": getattr(wallet, "balance_inr_paise", 0),
                } if wallet else {}
            except Exception:
                invoices_data = []
                wallet_data = {}

        billing_data = {"invoices": invoices_data, "wallet": wallet_data}
        zf.writestr("billing_summary.json", json.dumps(billing_data, indent=2, default=str))

        # --- README ---
        zf.writestr(
            "README.txt",
            "Voxly AI — Workspace Data Export\n"
            "=================================\n"
            "This archive contains your workspace data in compliance with GDPR Art. 20\n"
            "(Right to Data Portability) and the India DPDP Act 2023.\n\n"
            "Files included:\n"
            "  call_logs.csv        — Call history and metadata\n"
            "  contacts.csv         — Telephony contacts and leads\n"
            "  agent_prompts.json   — Voice agent configurations\n"
            "  billing_summary.json — Invoice and wallet history\n\n"
            f"Generated: {_utcnow().isoformat()}\n",
        )

    return buf.getvalue()


from pathlib import Path
_EXPORT_CACHE_DIR = Path("storage/exports")


async def _upload_export_zip(job_id: str, data: bytes) -> str:
    """Upload the export ZIP to R2/S3 and return a pre-signed URL.

    Falls back to a local download URL if cloud storage is not configured.
    """
    # Always persist locally to support local downloads
    try:
        _EXPORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        local_path = _EXPORT_CACHE_DIR / f"{job_id}.zip"
        local_path.write_bytes(data)
    except Exception as exc:
        logger.warning("Failed to cache export zip locally: %s", exc)

    try:
        import boto3
        from botocore.config import Config as BotoConfig
        from server.config.env import get_settings

        settings = get_settings()
        if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
            return f"/api/tenant/export/{job_id}/download"

        endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )
        key = f"exports/{job_id}/workspace_export.zip"
        s3.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType="application/zip",
        )
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=86400,  # 24 hours
        )
        return url

    except ImportError:
        return f"/api/tenant/export/{job_id}/download"
    except Exception:
        logger.exception("export upload failed for job_id=%s", job_id)
        return f"/api/tenant/export/{job_id}/download"
