"""SaaS identity and telephony commerce models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.db.models.entities import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class KycVerification(Base):
    """Didit KYC state for one user.

    `status` mirrors Didit's session status literals exactly ("Not Started" |
    "In Progress" | "Awaiting User" | "In Review" | "Approved" | "Declined" |
    "Resubmitted" | "Abandoned" | "Expired" | "Kyc Expired") because those are the
    dispatch keys in the webhook handler.

    Only the signature-verified webhook writes `status`. The create-session
    response and the browser return-trip are hints, never proof of approval.
    """

    __tablename__ = "kyc_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Not Started")
    didit_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class VobizSubaccount(Base):
    """Tenant-owned Vobiz customer_use account and carrier KYC state."""

    __tablename__ = "vobiz_subaccounts"
    __table_args__ = (UniqueConstraint("auth_id", name="uq_vobiz_subaccounts_auth_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        primary_key=True,
    )
    auth_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    encrypted_auth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_auth_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    account_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    application_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kyc_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    encrypted_kyc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    kyc_session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kyc_session_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_type: Mapped[str] = mapped_column(String(40), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    provisioning_status: Mapped[str] = mapped_column(String(32), nullable=False, default="creating")
    kyc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    kyc_calls_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_status_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_tenant_membership"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Sliding-window enforcement: last moment this token was actually presented. A
    # refresh older than SESSION_IDLE_TIMEOUT_MINUTES is refused server-side, so an
    # unattended tab cannot hold a live session for the whole 30-day token lifetime
    # just because something in the page re-issued the cookie.
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    # Absolute ceiling for one sign-in regardless of activity (SOC2 / OWASP: force a
    # full re-auth at least this often).
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    otp_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TenantTeardownJob(Base):
    """Multi-stage idempotent teardown pipeline record for a quarantined tenant.

    Stages: queued → integrations → subscriptions → carrier_numbers → storage
            → database → cache → verification → done

    Crash-safe: ``stage`` is checkpointed before each stage executes so a worker
    crash resumes at the exact stage rather than restarting from scratch.
    Distributed-lock-safe: ``locked_by`` / ``locked_until`` prevent two workers
    from processing the same job simultaneously.
    """

    __tablename__ = "tenant_teardown_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    # Canonical stage enum (matches migration + worker)
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Distributed lock: worker ID that holds the lock and its expiry
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Idempotency key: teardown:{tenant_id}:{epoch_of_deleted_at}
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TenantExportJob(Base):
    """Data-takeout (GDPR Art. 20) export job for a tenant workspace.

    Background worker generates an encrypted ZIP with call_logs.csv, contacts.csv,
    agent_prompts.json, and billing_summary.json; ``download_url`` is a time-limited
    pre-signed URL valid for 24 hours and audit-logged on access.
    """

    __tablename__ = "tenant_export_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    download_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NumberCatalog(Base):
    __tablename__ = "number_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    number_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NumberPurchase(Base):
    __tablename__ = "number_purchases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    e164: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), default="IN")
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    carrier_number_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assign_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class NumberReservation(Base):
    """Holds an E.164 while a purchase is in flight.

    Uniquely indexed on `e164` so two concurrent buyers of the same number cannot
    both pass the "is it reserved?" check — the second insert raises instead of
    silently double-selling the DID.
    """

    __tablename__ = "number_reservations"
    __table_args__ = (
        UniqueConstraint("e164", name="uq_number_reservations_e164_live"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    e164: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    purchase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("number_purchases.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProvisionJob(Base):
    __tablename__ = "provision_jobs"
    __table_args__ = (UniqueConstraint("purchase_id", name="uq_provision_job_purchase"),)

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("number_purchases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class StripeWebhookEvent(Base):
    __tablename__ = "stripe_webhook_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BillingWallet(Base):
    __tablename__ = "billing_wallets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), primary_key=True)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    balance_inr_paise: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TenantBillingProfile(Base):
    """Buyer identity used for GST place-of-supply and invoice legal fields.

    Held separately from `tenants` because a workspace can change its billing
    entity without changing the workspace, and because invoices snapshot these
    values at issue time and must never follow later edits.
    """

    __tablename__ = "tenant_billing_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), primary_key=True
    )
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    billing_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class PlatformTaxSettings(Base):
    """Singleton GST/invoice configuration the operator owns.

    Single row (`id=1`) rather than a version table: every invoice and order
    snapshots the values it was issued under, so changing this row can never
    alter a document that has already been issued.
    """

    __tablename__ = "platform_tax_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    trade_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    address_line2: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    state_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    state_code: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    postal_code: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")
    support_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    support_phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    sac_code: Mapped[str] = mapped_column(String(12), nullable=False, default="998413")
    default_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    #: When true, listed prices already contain GST; the wallet is credited with
    #: the net (taxable) portion and the customer is not charged extra at checkout.
    price_includes_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Export of services under LUT is zero-rated. Off only when the operator has
    #: not filed an LUT and must charge IGST on foreign supplies.
    export_zero_rated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invoice_prefix: Mapped[str] = mapped_column(String(4), nullable=False, default="INV")
    credit_note_prefix: Mapped[str] = mapped_column(String(4), nullable=False, default="CN")
    lut_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class InvoiceSequence(Base):
    """Consecutive serial numbers per financial year and document kind.

    GST Rule 46(b) requires a consecutive serial not exceeding 16 characters,
    unique for a financial year. The row is locked with `FOR UPDATE` while the
    number is allocated, so two concurrent payments cannot share a serial.
    """

    __tablename__ = "invoice_sequences"

    kind: Mapped[str] = mapped_column(String(4), primary_key=True)  # INV | CN
    fy: Mapped[str] = mapped_column(String(7), primary_key=True)  # 2026-27
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class BillingInvoice(Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (UniqueConstraint("invoice_number", name="uq_invoice_number"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Settled INR value of the taxable supply — what the wallet is credited.
    amount_inr_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Currency the customer was charged in, and the gross amount in minor units.
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Pre-tax and tax portions in the charge currency and in INR paise.
    taxable_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    taxable_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cgst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: cgst_sgst | igst | export | none
    tax_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    sac_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(120), nullable=True)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    customer_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    supplier_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    buyer_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: Financial year label and the serial within it, kept for reporting even if
    #: the display number format changes later.
    fy: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    line_items: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RazorpayOrder(Base):
    __tablename__ = "razorpay_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    #: What the wallet will be credited (taxable value in INR paise).
    amount_inr_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    #: Gross amount charged, in the charge currency's minor units.
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Checkout-time tax snapshot; never recomputed at payment time.
    gross_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    taxable_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tax_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    place_of_supply: Mapped[str | None] = mapped_column(String(120), nullable=True)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    buyer_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    supplier_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sac_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created")
    purpose: Mapped[str] = mapped_column(String(40), default="wallet_topup")
    payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Provider settlement data for reconciliation and costing.
    base_amount_inr_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tax_on_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settlement_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RazorpayWebhookEvent(Base):
    """Durable inbox for Razorpay webhooks.

    The provider retries on any non-2xx and may deliver the same event more than
    once; the event id primary key makes handling exactly-once even when two
    deliveries race.
    """

    __tablename__ = "razorpay_webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RazorpayRefund(Base):
    __tablename__ = "razorpay_refunds"

    refund_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    payment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    #: Wallet reversal and tax reversal in INR paise.
    credit_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processed")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CreditNote(Base):
    """GST credit note (CGST Sec 34) issued when a payment is refunded."""

    __tablename__ = "credit_notes"
    __table_args__ = (UniqueConstraint("credit_note_number", name="uq_credit_note_number"),)

    credit_note_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("billing_invoices.invoice_id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    credit_note_number: Mapped[str] = mapped_column(String(32), nullable=False)
    razorpay_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    gross_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    taxable_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cgst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sgst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    igst_inr_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    fy: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supplier_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    buyer_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="issued")
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BillingWalletTransaction(Base):
    __tablename__ = "billing_wallet_transactions"
    # Enforce idempotency at the DB level: two concurrent webhook retries with the
    # same reference_id cannot both commit. The IntegrityError catch in
    # billing_wallet_service.debit_wallet() relies on this constraint existing.
    # NULLs are intentionally excluded — Postgres treats NULLs as distinct, so
    # rows without a reference_id (e.g. manual top-ups) do not conflict.
    __table_args__ = (
        UniqueConstraint("reference_id", name="uq_billing_wallet_tx_reference_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_inr_paise: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Lead(Base):
    __tablename__ = "leads"

    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    #: Which AI employee produced this lead. Nullable: leads created by hand in the
    #: CRM, and leads that predate attribution, have no owner and stay visible to the
    #: workspace pipeline. Set for every lead the post-call pipeline writes.
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    stage: Mapped[str] = mapped_column(String(50), default="new")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TelephonyContact(Base):
    __tablename__ = "telephony_contacts"

    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserOnboardingSurvey(Base):
    __tablename__ = "user_onboarding_surveys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    referral_source: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_monthly_minutes: Mapped[str] = mapped_column(String(32), nullable=False)
    terms_and_telephony_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    terms_version: Mapped[str] = mapped_column(String(32), default="2026-10-v1", nullable=False)
    acceptable_use_version: Mapped[str] = mapped_column(String(32), default="2026-10-v1", nullable=False)
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BillingRateVersion(Base):
    """Versioned billing rates table. Never overwritten; changes append new versions."""

    __tablename__ = "billing_rate_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    pstn_rate_usd_cents_per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    web_agent_rate_usd_cents_per_min: Mapped[int] = mapped_column(Integer, nullable=False)
    did_monthly_usd_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    pstn_rate_usd_micros_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    web_agent_rate_usd_micros_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    did_monthly_usd_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_rate_inr_paise_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    web_agent_rate_inr_paise_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    did_monthly_inr_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_low_rate_usd_micros_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_low_rate_inr_paise_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_medium_rate_usd_micros_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_medium_rate_inr_paise_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_premium_rate_usd_micros_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pstn_premium_rate_inr_paise_per_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fx_rate_inr: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CustomerSupportConfig(Base):
    """Global customer support contact channels, social media links, and SLAs, configurable from admin panel."""

    __tablename__ = "customer_support_configs"

    config_key: Mapped[str] = mapped_column(String(64), primary_key=True, default="global")
    support_email: Mapped[str] = mapped_column(String(320), nullable=False, default="support@dialtact.com")
    support_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    business_hours: Mapped[str] = mapped_column(String(128), nullable=False, default="Mon - Fri: 9:00 AM - 6:00 PM EST")
    sla_response_time: Mapped[str] = mapped_column(String(128), nullable=False, default="Within 2 hours for Priority, 24 hours Standard")
    emergency_hotline: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    auto_reply_message: Mapped[str | None] = mapped_column(Text, nullable=True, default="Thank you for contacting Dialtact. A specialist has received your inquiry and will follow up shortly.")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Social Media Links (Configured via backend Admin Panel)
    twitter_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default="https://x.com/dialtact")
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default="https://linkedin.com/company/dialtact")
    github_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default="https://github.com/dialtact")
    youtube_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default="https://youtube.com/@dialtact")
    discord_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default="https://discord.gg/dialtact")

    # Mail / SMTP Gateway Settings (Configured via backend Admin Panel)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sender_email: Mapped[str | None] = mapped_column(String(320), nullable=True, default="support@dialtact.com")
    sender_name: Mapped[str | None] = mapped_column(String(128), nullable=True, default="Dialtact Support Desk")
    notify_customer_on_ticket: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_admin_on_ticket: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    admin_alert_email: Mapped[str | None] = mapped_column(String(320), nullable=True, default="support@dialtact.com")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SupportInquiry(Base):
    """Customer support inquiries and tickets submitted via Contact Us page and tenant console."""

    __tablename__ = "support_inquiries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="technical_support")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_replies: Mapped[list | None] = mapped_column(JSON, default=list)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


