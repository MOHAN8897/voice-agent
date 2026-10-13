"""Customer support flow service — backend persistence for support channels, social links, SMTP, and inquiries."""
from __future__ import annotations

import asyncio
import logging
import random
import smtplib
import string
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import desc, select

from server.db.connection import get_session_factory
from server.db.models.saas_models import CustomerSupportConfig, SupportInquiry

logger = logging.getLogger(__name__)

DEFAULT_SUPPORT_CONFIG = {
    "config_key": "global",
    "support_email": "support@dialtact.com",
    "support_phone": None,
    "business_hours": "Mon - Fri: 9:00 AM - 6:00 PM EST",
    "sla_response_time": "Within 2 hours for Priority, 24 hours Standard",
    "emergency_hotline": None,
    "auto_reply_message": "Thank you for contacting Dialtact. A support specialist has received your inquiry and will follow up shortly.",
    "is_active": True,
    "twitter_url": "https://x.com/dialtact",
    "linkedin_url": "https://linkedin.com/company/dialtact",
    "github_url": "https://github.com/dialtact",
    "youtube_url": "https://youtube.com/@dialtact",
    "discord_url": "https://discord.gg/dialtact",
    "smtp_host": None,
    "smtp_port": 587,
    "smtp_username": None,
    "smtp_password": None,
    "smtp_use_tls": True,
    "sender_email": "support@dialtact.com",
    "sender_name": "Dialtact Support Desk",
    "notify_customer_on_ticket": True,
    "notify_admin_on_ticket": True,
    "admin_alert_email": "support@dialtact.com",
}


def _generate_ticket_number() -> str:
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m")
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"DT-{date_part}-{random_part}"


def _send_smtp_sync(
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    use_tls: bool,
    from_addr: str,
    from_name: str,
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg["To"] = to_addr

        part1 = MIMEText(body_text, "plain")
        msg.attach(part1)

        if body_html:
            part2 = MIMEText(body_html, "html")
            msg.attach(part2)

        server = smtplib.SMTP(host, port, timeout=12)
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        return True
    except Exception as exc:
        logger.warning("SMTP email dispatch failed to %s: %s", to_addr, exc)
        return False


async def send_system_email(to_addr: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send an automated system email if SMTP is configured."""
    cfg = await get_support_config(for_admin=True)
    host = cfg.get("smtpHost")
    if not host:
        return False

    port = cfg.get("smtpPort") or 587
    username = cfg.get("smtpUsername")
    # Fetch real password from DB if not masked
    password = None
    factory = get_session_factory()
    if factory:
        try:
            async with factory() as session:
                stmt = select(CustomerSupportConfig.smtp_password).where(CustomerSupportConfig.config_key == "global")
                password = (await session.execute(stmt)).scalar_one_or_none()
        except Exception:
            pass

    use_tls = bool(cfg.get("smtpUseTls", True))
    from_addr = cfg.get("senderEmail") or "support@dialtact.com"
    from_name = cfg.get("senderName") or "Dialtact Support Desk"

    return await asyncio.to_thread(
        _send_smtp_sync,
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        from_addr=from_addr,
        from_name=from_name,
        to_addr=to_addr,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )


async def test_smtp_configuration(settings: dict) -> dict:
    """Verify SMTP host connection, TLS handshake, and authentication credentials."""
    host = settings.get("smtpHost")
    if not host:
        return {"success": False, "error": "SMTP Host is required"}

    port = int(settings.get("smtpPort") or 587)
    username = settings.get("smtpUsername")
    password = settings.get("smtpPassword")
    use_tls = bool(settings.get("smtpUseTls", True))

    # If password not provided in test payload, try loading persisted password
    if not password:
        factory = get_session_factory()
        if factory:
            try:
                async with factory() as session:
                    stmt = select(CustomerSupportConfig.smtp_password).where(CustomerSupportConfig.config_key == "global")
                    password = (await session.execute(stmt)).scalar_one_or_none()
            except Exception:
                pass

    def _probe_sync():
        try:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.noop()
            server.quit()
            return {"success": True, "message": "SMTP connection & authentication verified successfully."}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return await asyncio.to_thread(_probe_sync)


async def get_support_config(for_admin: bool = False) -> dict:
    """Retrieve support configuration. Public view hides admin/SMTP internals and omits phone numbers."""
    factory = get_session_factory()
    if not factory:
        return _format_config_dict(DEFAULT_SUPPORT_CONFIG, for_admin)

    try:
        async with factory() as session:
            stmt = select(CustomerSupportConfig).where(CustomerSupportConfig.config_key == "global")
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                row = CustomerSupportConfig(
                    config_key="global",
                    support_email=DEFAULT_SUPPORT_CONFIG["support_email"],
                    business_hours=DEFAULT_SUPPORT_CONFIG["business_hours"],
                    sla_response_time=DEFAULT_SUPPORT_CONFIG["sla_response_time"],
                    auto_reply_message=DEFAULT_SUPPORT_CONFIG["auto_reply_message"],
                    is_active=DEFAULT_SUPPORT_CONFIG["is_active"],
                    twitter_url=DEFAULT_SUPPORT_CONFIG["twitter_url"],
                    linkedin_url=DEFAULT_SUPPORT_CONFIG["linkedin_url"],
                    github_url=DEFAULT_SUPPORT_CONFIG["github_url"],
                    youtube_url=DEFAULT_SUPPORT_CONFIG["youtube_url"],
                    discord_url=DEFAULT_SUPPORT_CONFIG["discord_url"],
                    smtp_host=DEFAULT_SUPPORT_CONFIG["smtp_host"],
                    smtp_port=DEFAULT_SUPPORT_CONFIG["smtp_port"],
                    smtp_username=DEFAULT_SUPPORT_CONFIG["smtp_username"],
                    smtp_password=DEFAULT_SUPPORT_CONFIG["smtp_password"],
                    smtp_use_tls=DEFAULT_SUPPORT_CONFIG["smtp_use_tls"],
                    sender_email=DEFAULT_SUPPORT_CONFIG["sender_email"],
                    sender_name=DEFAULT_SUPPORT_CONFIG["sender_name"],
                    notify_customer_on_ticket=DEFAULT_SUPPORT_CONFIG["notify_customer_on_ticket"],
                    notify_admin_on_ticket=DEFAULT_SUPPORT_CONFIG["notify_admin_on_ticket"],
                    admin_alert_email=DEFAULT_SUPPORT_CONFIG["admin_alert_email"],
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)

            return _format_config_row(row, for_admin)
    except Exception as exc:
        logger.warning("Failed to fetch CustomerSupportConfig from DB: %s", exc)
        return _format_config_dict(DEFAULT_SUPPORT_CONFIG, for_admin)


def _format_config_row(row: CustomerSupportConfig, for_admin: bool) -> dict:
    base = {
        "configKey": row.config_key,
        "supportEmail": row.support_email,
        "businessHours": row.business_hours,
        "slaResponseTime": row.sla_response_time,
        "autoReplyMessage": row.auto_reply_message,
        "isActive": row.is_active,
        "socialLinks": {
            "twitter": row.twitter_url or "https://x.com/dialtact",
            "linkedin": row.linkedin_url or "https://linkedin.com/company/dialtact",
            "github": row.github_url or "https://github.com/dialtact",
            "youtube": row.youtube_url or "https://youtube.com/@dialtact",
            "discord": row.discord_url or "https://discord.gg/dialtact",
        },
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }

    if not for_admin:
        return base

    # Admin view includes editable social links and SMTP gateway parameters
    base.update({
        "twitterUrl": row.twitter_url,
        "linkedinUrl": row.linkedin_url,
        "githubUrl": row.github_url,
        "youtubeUrl": row.youtube_url,
        "discordUrl": row.discord_url,
        "smtpHost": row.smtp_host,
        "smtpPort": row.smtp_port or 587,
        "smtpUsername": row.smtp_username,
        "smtpHasPassword": bool(row.smtp_password),
        "smtpUseTls": bool(row.smtp_use_tls),
        "senderEmail": row.sender_email,
        "senderName": row.sender_name,
        "notifyCustomerOnTicket": bool(row.notify_customer_on_ticket),
        "notifyAdminOnTicket": bool(row.notify_admin_on_ticket),
        "adminAlertEmail": row.admin_alert_email,
    })
    return base


def _format_config_dict(d: dict, for_admin: bool) -> dict:
    base = {
        "configKey": d["config_key"],
        "supportEmail": d["support_email"],
        "businessHours": d["business_hours"],
        "slaResponseTime": d["sla_response_time"],
        "autoReplyMessage": d["auto_reply_message"],
        "isActive": d["is_active"],
        "socialLinks": {
            "twitter": d.get("twitter_url") or "https://x.com/dialtact",
            "linkedin": d.get("linkedin_url") or "https://linkedin.com/company/dialtact",
            "github": d.get("github_url") or "https://github.com/dialtact",
            "youtube": d.get("youtube_url") or "https://youtube.com/@dialtact",
            "discord": d.get("discord_url") or "https://discord.gg/dialtact",
        },
        "updatedAt": None,
    }
    if not for_admin:
        return base

    base.update({
        "twitterUrl": d.get("twitter_url"),
        "linkedinUrl": d.get("linkedin_url"),
        "githubUrl": d.get("github_url"),
        "youtubeUrl": d.get("youtube_url"),
        "discordUrl": d.get("discord_url"),
        "smtpHost": d.get("smtp_host"),
        "smtpPort": d.get("smtp_port") or 587,
        "smtpUsername": d.get("smtp_username"),
        "smtpHasPassword": bool(d.get("smtp_password")),
        "smtpUseTls": bool(d.get("smtp_use_tls", True)),
        "senderEmail": d.get("sender_email"),
        "senderName": d.get("sender_name"),
        "notifyCustomerOnTicket": bool(d.get("notify_customer_on_ticket", True)),
        "notifyAdminOnTicket": bool(d.get("notify_admin_on_ticket", True)),
        "adminAlertEmail": d.get("admin_alert_email"),
    })
    return base


async def update_support_config(updates: dict) -> dict:
    """Update global customer support channels, social links, and SMTP configuration."""
    factory = get_session_factory()
    if not factory:
        raise RuntimeError("Database connection unavailable")

    async with factory() as session:
        async with session.begin():
            stmt = select(CustomerSupportConfig).where(CustomerSupportConfig.config_key == "global").with_for_update()
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                row = CustomerSupportConfig(config_key="global")
                session.add(row)

            if "supportEmail" in updates and updates["supportEmail"]:
                row.support_email = str(updates["supportEmail"]).strip()
            if "businessHours" in updates and updates["businessHours"]:
                row.business_hours = str(updates["businessHours"]).strip()
            if "slaResponseTime" in updates and updates["slaResponseTime"]:
                row.sla_response_time = str(updates["slaResponseTime"]).strip()
            if "autoReplyMessage" in updates:
                row.auto_reply_message = str(updates["autoReplyMessage"]).strip() if updates["autoReplyMessage"] else None
            if "isActive" in updates:
                row.is_active = bool(updates["isActive"])

            # Social Links
            if "twitterUrl" in updates:
                row.twitter_url = str(updates["twitterUrl"]).strip() if updates["twitterUrl"] else None
            if "linkedinUrl" in updates:
                row.linkedin_url = str(updates["linkedinUrl"]).strip() if updates["linkedinUrl"] else None
            if "githubUrl" in updates:
                row.github_url = str(updates["githubUrl"]).strip() if updates["githubUrl"] else None
            if "youtubeUrl" in updates:
                row.youtube_url = str(updates["youtubeUrl"]).strip() if updates["youtubeUrl"] else None
            if "discordUrl" in updates:
                row.discord_url = str(updates["discordUrl"]).strip() if updates["discordUrl"] else None

            # Mail / SMTP Gateway Settings
            if "smtpHost" in updates:
                row.smtp_host = str(updates["smtpHost"]).strip() if updates["smtpHost"] else None
            if "smtpPort" in updates and updates["smtpPort"] is not None:
                row.smtp_port = int(updates["smtpPort"])
            if "smtpUsername" in updates:
                row.smtp_username = str(updates["smtpUsername"]).strip() if updates["smtpUsername"] else None
            if "smtpPassword" in updates and updates["smtpPassword"]:
                row.smtp_password = str(updates["smtpPassword"]).strip()
            if "smtpUseTls" in updates:
                row.smtp_use_tls = bool(updates["smtpUseTls"])
            if "senderEmail" in updates:
                row.sender_email = str(updates["senderEmail"]).strip() if updates["senderEmail"] else None
            if "senderName" in updates:
                row.sender_name = str(updates["senderName"]).strip() if updates["senderName"] else None
            if "notifyCustomerOnTicket" in updates:
                row.notify_customer_on_ticket = bool(updates["notifyCustomerOnTicket"])
            if "notifyAdminOnTicket" in updates:
                row.notify_admin_on_ticket = bool(updates["notifyAdminOnTicket"])
            if "adminAlertEmail" in updates:
                row.admin_alert_email = str(updates["adminAlertEmail"]).strip() if updates["adminAlertEmail"] else None

            row.updated_at = datetime.now(timezone.utc)

        await session.refresh(row)
        return _format_config_row(row, for_admin=True)


async def create_support_inquiry(
    full_name: str,
    email: str,
    subject: str,
    message: str,
    phone: str | None = None,
    company: str | None = None,
    category: str = "technical_support",
    priority: str = "normal",
    tenant_id: uuid.UUID | None = None,
) -> dict:
    """Save customer inquiry and return assigned ticket number, dispatching notifications if SMTP enabled."""
    factory = get_session_factory()
    ticket_num = _generate_ticket_number()
    inquiry_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    if factory:
        async with factory() as session:
            async with session.begin():
                inquiry = SupportInquiry(
                    id=inquiry_id,
                    ticket_number=ticket_num,
                    tenant_id=tenant_id,
                    full_name=full_name.strip(),
                    email=email.strip().lower(),
                    phone=phone.strip() if phone else None,
                    company=company.strip() if company else None,
                    category=category.strip() if category else "technical_support",
                    priority=priority.strip() if priority else "normal",
                    subject=subject.strip(),
                    message=message.strip(),
                    status="new",
                    customer_replies=[],
                    tags=[category.strip()] if category else [],
                    created_at=now,
                    updated_at=now,
                )
                session.add(inquiry)

    # Trigger async notification emails in the background
    asyncio.create_task(_dispatch_new_ticket_notifications(ticket_num, full_name, email, subject, message))

    return {
        "id": str(inquiry_id),
        "ticketNumber": ticket_num,
        "fullName": full_name,
        "email": email,
        "category": category,
        "priority": priority,
        "subject": subject,
        "status": "new",
        "createdAt": now.isoformat(),
    }


async def _dispatch_new_ticket_notifications(
    ticket_number: str,
    full_name: str,
    customer_email: str,
    subject: str,
    message: str,
) -> None:
    try:
        cfg = await get_support_config(for_admin=True)
        # 1. Customer confirmation
        if cfg.get("notifyCustomerOnTicket"):
            ack_subject = f"[{ticket_number}] Dialtact Support Request Received: {subject}"
            ack_text = (
                f"Hello {full_name},\n\n"
                f"Thank you for contacting Dialtact Customer Support.\n"
                f"Your request has been registered under Ticket ID: {ticket_number}\n\n"
                f"Subject: {subject}\n"
                f"SLA Target: {cfg.get('slaResponseTime', 'Within 2 hours')}\n\n"
                f"A voice support engineer will review your ticket and reply directly to this thread.\n\n"
                f"---\nDialtact Support Desk\nsupport@dialtact.com"
            )
            await send_system_email(to_addr=customer_email, subject=ack_subject, body_text=ack_text)

        # 2. Admin alert
        if cfg.get("notifyAdminOnTicket") and cfg.get("adminAlertEmail"):
            admin_subject = f"[New Ticket Alert] {ticket_number} - {subject}"
            admin_text = (
                f"New customer ticket opened:\n"
                f"Ticket ID: {ticket_number}\n"
                f"Contact: {full_name} ({customer_email})\n"
                f"Subject: {subject}\n\n"
                f"Message:\n{message}\n"
            )
            await send_system_email(to_addr=cfg["adminAlertEmail"], subject=admin_subject, body_text=admin_text)
    except Exception as exc:
        logger.debug("Ticket notification dispatch skipped: %s", exc)


async def list_support_inquiries(
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List customer support inquiries for platform admin with advanced filtering."""
    factory = get_session_factory()
    if not factory:
        return []

    async with factory() as session:
        query = select(SupportInquiry)
        if status and status != "all":
            query = query.where(SupportInquiry.status == status)
        if priority and priority != "all":
            query = query.where(SupportInquiry.priority == priority)
        if category and category != "all":
            query = query.where(SupportInquiry.category == category)
        if search:
            s_term = f"%{search.strip().lower()}%"
            query = query.where(
                (SupportInquiry.ticket_number.ilike(s_term))
                | (SupportInquiry.email.ilike(s_term))
                | (SupportInquiry.full_name.ilike(s_term))
                | (SupportInquiry.subject.ilike(s_term))
            )

        query = query.order_by(desc(SupportInquiry.created_at)).offset(offset).limit(limit)
        rows = (await session.execute(query)).scalars().all()

        return [
            {
                "id": str(r.id),
                "ticketNumber": r.ticket_number,
                "tenantId": str(r.tenant_id) if r.tenant_id else None,
                "fullName": r.full_name,
                "email": r.email,
                "company": r.company,
                "category": r.category,
                "priority": r.priority,
                "subject": r.subject,
                "message": r.message,
                "status": r.status,
                "assignedTo": r.assigned_to,
                "adminNotes": r.admin_notes,
                "resolutionNotes": r.resolution_notes,
                "customerReplies": r.customer_replies or [],
                "tags": r.tags or [],
                "createdAt": r.created_at.isoformat() if r.created_at else None,
                "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


async def get_support_inquiry_detail(inquiry_id: uuid.UUID) -> dict | None:
    """Retrieve complete inquiry details including conversation thread and tenant association."""
    factory = get_session_factory()
    if not factory:
        return None

    async with factory() as session:
        stmt = select(SupportInquiry).where(SupportInquiry.id == inquiry_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if not row:
            return None

        return {
            "id": str(row.id),
            "ticketNumber": row.ticket_number,
            "tenantId": str(row.tenant_id) if row.tenant_id else None,
            "fullName": row.full_name,
            "email": row.email,
            "company": row.company,
            "category": row.category,
            "priority": row.priority,
            "subject": row.subject,
            "message": row.message,
            "status": row.status,
            "assignedTo": row.assigned_to,
            "adminNotes": row.admin_notes,
            "resolutionNotes": row.resolution_notes,
            "customerReplies": row.customer_replies or [],
            "tags": row.tags or [],
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        }


async def update_support_inquiry(
    inquiry_id: uuid.UUID,
    status: str | None = None,
    assigned_to: str | None = None,
    admin_notes: str | None = None,
    resolution_notes: str | None = None,
    reply_message: str | None = None,
    reply_author: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update status, assignee, notes, or append a customer reply to an inquiry ticket."""
    factory = get_session_factory()
    if not factory:
        raise RuntimeError("Database connection unavailable")

    async with factory() as session:
        async with session.begin():
            stmt = select(SupportInquiry).where(SupportInquiry.id == inquiry_id).with_for_update()
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                raise ValueError("Inquiry not found")

            if status:
                row.status = status.strip().lower()
            if assigned_to is not None:
                row.assigned_to = assigned_to.strip() if assigned_to else None
            if admin_notes is not None:
                row.admin_notes = admin_notes.strip()
            if resolution_notes is not None:
                row.resolution_notes = resolution_notes.strip()
            if tags is not None:
                row.tags = tags

            customer_email = row.email
            ticket_number = row.ticket_number
            subject = row.subject

            if reply_message and reply_message.strip():
                now = datetime.now(timezone.utc).isoformat()
                author_name = reply_author.strip() if reply_author else "Support Desk"
                new_reply = {
                    "id": str(uuid.uuid4())[:8],
                    "author": author_name,
                    "message": reply_message.strip(),
                    "sentAt": now,
                    "isStaff": True,
                }
                current_replies = list(row.customer_replies or [])
                current_replies.append(new_reply)
                row.customer_replies = current_replies

                # Send email reply to customer
                asyncio.create_task(
                    _dispatch_customer_reply_email(
                        customer_email=customer_email,
                        ticket_number=ticket_number,
                        subject=subject,
                        author_name=author_name,
                        reply_message=reply_message.strip(),
                    )
                )

            row.updated_at = datetime.now(timezone.utc)

        await session.refresh(row)
        return {
            "id": str(row.id),
            "ticketNumber": row.ticket_number,
            "status": row.status,
            "assignedTo": row.assigned_to,
            "adminNotes": row.admin_notes,
            "resolutionNotes": row.resolution_notes,
            "customerReplies": row.customer_replies or [],
            "tags": row.tags or [],
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        }


async def _dispatch_customer_reply_email(
    customer_email: str,
    ticket_number: str,
    subject: str,
    author_name: str,
    reply_message: str,
) -> None:
    try:
        email_subject = f"Re: [{ticket_number}] {subject}"
        email_body = (
            f"Hello,\n\n"
            f"A member of our support engineering desk has responded to your ticket {ticket_number}:\n\n"
            f"\"{reply_message}\"\n\n"
            f"---\n"
            f"{author_name}\n"
            f"Dialtact Support Desk\n"
            f"support@dialtact.com\n"
        )
        await send_system_email(to_addr=customer_email, subject=email_subject, body_text=email_body)
    except Exception as exc:
        logger.debug("Failed to dispatch customer reply email: %s", exc)
