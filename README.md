# Dialtact AI — Enterprise Autonomous Voice Agent & Multi-Tenant Telephony SaaS

[![Security SAST](https://img.shields.io/badge/Security-SAST%20Zero%20Findings-success)](scripts/security_audit.py)
[![Telephony](https://img.shields.io/badge/Telephony-Vobiz%20Primary%20%7C%20Telnyx%20Secondary-blue)]()
[![Voice Core](https://img.shields.io/badge/Voice%20Core-Gemini%20Live%20Streaming-orange)]()
[![License](https://img.shields.io/badge/License-Proprietary-red)]()

Dialtact AI is a production-grade, multi-tenant conversational Voice AI platform providing ultra-low-latency bidirectional phone calls, automated outbound campaign management, intelligent business brain knowledge bases, and telecom carrier subaccount isolation.

---

## 🌟 Architecture Overview

```
                                      +------------------------------------+
                                      |          Platform Ops / Admins     |
                                      +-----------------+------------------+
                                                        |
                                                        v
                                          +-----------------------------+
                                          |   Next.js Dev Admin Portal  |
                                          |  (/dev/admin/compliance)    |
                                          +--------------+--------------+
                                                         |
                                                         v
+-------------------------------+               +-----------------+----------------+
|       Tenant Voice Console    | <===========> |        FastAPI Backend Core      |
|    (dialtact-app React 18 SPA)    |   REST / WS   |   (SQLAlchemy Async + Redis)     |
+-------------------------------+               +-----------------+----------------+
                                                                  |
                                      +---------------------------+---------------------------+
                                      |                                                       |
                                      v                                                       v
                       +-------------------------------+                       +-------------------------------+
                       |    Vobiz Voice Carrier Stack  |                       |       Gemini Live Engine      |
                       |  - Subaccounts (Customer Use) |                       |  - Bidirectional Audio Stream |
                       |  - Hosted Regulatory KYC      |                       |  - Realtime Speech-to-Speech  |
                       |  - PSTN Direct Voice Trunks   |                       |  - Business Brain Compilation |
                       +-------------------------------+                       +-------------------------------+
```

---

## 🚀 Recent Updates & Major Changelog (October 2026)

### 1. Vobiz Voice KYC & Subaccount Onboarding Flow
- **Carrier-Hosted Compliance Integration**: Implemented complete regulatory KYC onboarding backed by Vobiz’s hosted verification flow for Indian telecom regulations.
- **Tenant Subaccount Isolation**: Every workspace automatically receives an isolated `customer_use` child subaccount under the platform parent account.
- **Credential Protection**: One-time child authentication tokens are encrypted using dedicated Fernet cryptography (`VOBIZ_SUBACCOUNT_ENCRYPTION_KEY`) and never leaked to the browser.
- **Document Verification Support**: Tracks status for required entity documentation including Individual Aadhaar, Corporate PAN, GSTIN, and Authorized Signatory declarations.

### 2. Frontend Session Preservation & Clean Verification Flow
- **Seamless Window Management**: In `PhoneNumbersModule.jsx`, hosted verification now triggers in an isolated window/tab or modal without navigating away from the active workspace.
- **Eliminated Spurious Logouts**: Fixed session drop issue where redirect callbacks from external carrier verification caused `WorkspaceContext` token eviction and logged out the user.
- **Actionable Purchase Feedback**: Added live carrier balance verification and surfaced clear error messaging (*"Purchase failed. Please check carrier balance or contact support"*) instead of ambiguous server 500 exceptions.

### 3. Subaccount Management & Phone Number Allocation
- **Hierarchical Governance**: Master administrative credentials remain strictly privileged to the platform parent account.
- **Dedicated Inventory**: Numbers purchased by a tenant subaccount are assigned directly to that tenant in `saas_phone_numbers`.
- **Telecom Cooldown Rules**: Enforces carrier-mandated 15-day cooldown periods after active call traffic to prevent telecom routing misconfigurations and carrier lockouts.

### 4. Admin Portal Shift from Didit to Vobiz Voice KYC
- **Unified Compliance Queue (`GET /api/dev/admin/kyc`)**: Shifted the primary admin verification queue from legacy Didit-only queries to unified Vobiz Voice KYC subaccounts, placing active telecom verifications at the top of the queue.
- **Verification Panel (`VerificationPanel.tsx`)**: Added dual telemetry metrics separating **Telephony KYC (Vobiz)** from **Identity Verification (Didit)**. Displays legal business names, corporate entity badges, call restriction flags, and document checks.
- **Tenant Detail Cockpit (`tenants/[tenantId]/page.tsx`)**: Added a dedicated **Telephony Voice KYC** card in the Compliance view showing calling gate pass status (`ENABLED` vs `BLOCKED`), provisioning state, and subaccount Auth IDs.
- **Status Override Normalization**: Updated `admin_set_voice_kyc_status()` to accept both human labels (`"Approved"`, `"Declined"`, `"In Review"`) and internal database tokens (`"verified"`, `"failed"`, `"pending"`).

### 5. Security Hardening & Zero-Vulnerability Invariants
- **SAST Audit Compliance**: Executed full codebase scans with `scripts/security_audit.py --mode sast` — **0 findings, 0 blocking issues** across 1,291 files.
- **Audit Justification Enforcement**: Added mandatory 8+ character justification statements (`statement_required`) on all admin status changes for SOC2 and regulatory compliance.
- **Carrier Guard on Call Passing**: Protected `assert_voice_kyc_approved()` with active carrier checks to prevent false call blocking on secondary carriers.
- **Zero Carrier Credential Leakage**: Public and tenant APIs strictly scrub wholesale carrier names, Auth IDs, internal webhooks, and private encryption keys.

---

## 🛠️ Verification & Quality Gates

```bash
# 1. Run Vobiz subaccount lifecycle tests (51 passed)
pytest server/tests/test_vobiz_subaccount_lifecycle.py

# 2. Run TypeScript build verification
cd web && npx tsc --noEmit

# 3. Run Static Application Security Testing (SAST)
python scripts/security_audit.py --mode sast
```

---

## 📄 Documentation Links
- [Tenant Phone Onboarding Architecture](docs/vobiz-tenant-onboarding.md)
- [Voice KYC & Subaccount Unification Changelog](docs/changelog/2026-10-kyc-subaccount-and-admin-unification.md)
- [PSTN Live Diagnostics & Call Tracing](docs/PSTN_LIVE_DIAGNOSTICS.md)
- [Campaign Operations Guide](docs/CAMPAIGN_OPERATIONS.md)