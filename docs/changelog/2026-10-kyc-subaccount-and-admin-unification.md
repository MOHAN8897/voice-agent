# Changelog: Vobiz Voice KYC, Subaccount Lifecycle & Admin Panel Unification

**Date**: 2026-10-21  
**Author**: Senior Staff Engineering & Security Audit  
**Branch**: `working-app-19-10-2026`  
**Target Systems**: `server` (FastAPI / SQLAlchemy), `voxly-ai` (React Console), `web` (Next.js Dev Portal)

---

## 1. Executive Summary

This release unifies the tenant telephony onboarding and regulatory compliance infrastructure around **Vobiz Voice KYC & Subaccounts**, eliminates operational blind spots in the Admin Dev Portal, hardens tenant authentication against spurious logouts during KYC redirects, and secures number purchase and inventory allocation.

---

## 2. Key Changes by Subsystem

### A. Frontend Tenant Console (`voxly-ai`)
- **Hosted KYC Redirect & Window Handling**:
  - Hosted verification flow in `PhoneNumbersModule.jsx` updated to launch securely in an isolated window/tab or non-destructive modal without navigating away from the active workspace.
  - Mitigated session drop: Returning from the external carrier KYC portal preserves local authentication state, preventing spurious `/login` logouts.
- **Phone Number Purchase & Error Handling**:
  - Hardened number purchasing flow: Validates subaccount balance, verifies KYC clearance, and provisions default inbound applications before attempting number acquisition.
  - Replaced ambiguous 500 error popups with actionable feedback: *"Purchase failed. Please check carrier account balance or contact support."*

### B. Subaccount Architecture & Number Lifecycle
- **Parent-Child Hierarchy**:
  - Each tenant receives a distinct `customer_use` child subaccount under the platform's master Vobiz account.
  - The parent account retains ultimate administrative control, billing consolidation, and master API key privileges.
- **Number Allocation & Unassignment**:
  - Numbers purchased through the subaccount are tied to the tenant in `saas_phone_numbers` and the carrier registry.
  - Unassignment and reallocation adhere to carrier-mandated cool-off periods (15 days post-traffic) to prevent telecom routing misconfigurations and carrier lockouts.

### C. Backend Admin Dev Portal (`server/routes/dev_admin.py` & `web`)
- **Queue Shift from Didit to Vobiz Voice KYC**:
  - `GET /api/dev/admin/kyc`: Unified compliance queue. Previously only fetched Didit identity records; now queries both `list_voice_verifications()` and Didit, prioritizing active Vobiz Voice KYC subaccounts at the top.
  - `GET /api/dev/admin/tenants/{tenant_id}`: Returns live `voiceKyc` state including legal entity type, subaccount Auth ID, document verification status (Aadhaar, PAN, GST), and calling gate status.
- **Admin Verification Panel (`VerificationPanel.tsx`)**:
  - Added dedicated metric cards for **Telephony KYC (Vobiz)** vs. **Identity Verification (Didit)**.
  - Displays business legal entity names, corporate structure tags, calls-blocked alerts, and document badges.
- **Tenant Detail Cockpit (`tenants/[tenantId]/page.tsx`)**:
  - Added dedicated **Telephony Voice KYC (Vobiz Subaccount)** compliance card with live status inspection and calling gate controls.

---

## 3. Vulnerability Remediation & Security Audit

| Vulnerability | Severity | Remediation |
| :--- | :--- | :--- |
| **Admin Visibility Blackout** | High | Added `list_voice_verifications()` to surface all tenant Vobiz KYC records in `/dev/admin/compliance`. |
| **Status Mapping 400 Mismatch** | Medium | Normalized input in `admin_set_voice_kyc_status()` to accept both human labels (`"approved"`, `"declined"`) and internal tokens (`"verified"`, `"failed"`). |
| **Missing Audit Justification** | Medium | Enforced an 8+ character justification requirement (`statement_required`) on all admin verification status changes. |
| **Secondary Carrier Call Blocking** | Medium | Added provider check in `assert_voice_kyc_approved()` so non-Vobiz carriers (Telnyx) are not erroneously gated. |
| **Carrier Secrets Scrubbing** | High | Stripped all carrier auth tokens and encryption keys from public and tenant API projections. |

---

## 4. Verification & Testing

- **Automated Tests**: `pytest server/tests/test_vobiz_subaccount_lifecycle.py` — 51 passed.
- **TypeScript Verification**: `npx tsc --noEmit` across Next.js admin portal — 0 errors.
- **SAST Security Audit**: `python scripts/security_audit.py --mode sast` — 0 findings, 0 blocking issues across 1,291 files.
