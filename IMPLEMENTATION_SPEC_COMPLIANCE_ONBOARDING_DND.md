# Engineering Specification: 5-Phase Implementation Blueprint
## Compliance Attestation, Post-Prewarm Recording Disclosure, Normalized Onboarding vs. Settings Isolation, Tenant-Wide Authoritative Pre-Dial DND & Audit-Preserved Soft Deactivation

**Document Version:** 2.1.0  
**Target Systems:** FastAPI Backend (`server/`), Vite React Console (`voxly-ai/`), Next.js Web App (`web/`)  
**Compliance Standards:** FTC Telemarketing Sales Rule (TSR), Telephone Consumer Protection Act (TCPA), OWASP ASVS, SOC2 Security & Privacy  
**Tooling & Verification:** Chisle Efficiency Ladder, Reticle In-App Browser Verification, Pytest Backend Suite, Playwright E2E  

---

## 1. Architectural Architecture & Core Principles

```
                                  TENANT / OPERATOR
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
          Agent Studio Console                           Global Campaigns Module
     (`Calls` → `Outbound` / `Settings`)                 (`CampaignsModule.jsx`)
                  │                                               │
                  │ [Toggle & Edit]                               │ [Launch Campaign]
                  ▼                                               ▼
       Recording Disclosure Card                       Campaign Compliance Modal
   (Post-Prewarm Live Turn Policy)                 (Mandatory Legal Attestation)
   "This call may be recorded..."                  "I confirm authorization..."
                  │                                               │
                  ▼                                               ▼
     Agent Script Compiler (`v18`)                    DB `campaigns` Audit Record
  "Weave disclosure into Turn 1"                      (attested_at, ip, version)
                  │                                               │
                  ▼                                               ▼
              LIVE CALL                              Queue Contacts for Campaign
   Instant Prewarm Greeting Audio                                 │
                  │                                               ▼
                  │ Caller Responds                  RIGHT BEFORE DIALING CONTACT
                  ▼                                               │
       Turn 1: Natural Disclosure                                 ▼
         + Answer Caller Inquiry                      Authoritative Tenant-Wide DND Check
                  │                                  (SELECT 1 FROM dnc_list WHERE...)
                  │ Caller says "stop calling"                    │
                  ▼                                       ┌───────┴───────┐
      Automated DND Auto-Enrollment                       ▼               ▼
      Tenant-Wide (`dnc_list`)                         In DND?         Not in DND?
                  │                                  (active=True)         │
                  ▼                                       │                ▼
      BLOCKED ACROSS ALL AGENTS                           ▼           Proceed with
      (Agent A, Agent B, Agent C,                      SKIP DIAL       _dial_one()
       Campaigns, & Single Outbound)               (status='dnc_excluded')
```

### Core Architectural Guarantees:

1. **Authoritative Pre-Dial DND Filter (Eliminating Race Conditions):**
   * Pre-campaign scrubbing at creation time is **not enough**. If a campaign is created at 10:00 AM, a contact requests opt-out at 10:01 AM, and the runner starts at 10:02 AM, relying on a snapshot would result in an illegal call.
   * **The authoritative DND check executes at the last possible millisecond immediately before dialing** in `server/services/saas/campaign_runner.py` and single-dial handlers.
   * If a contact is active in `dnc_list`, the runner immediately skips the number, records `status="dnc_excluded"`, increments `dnc_skipped` telemetry, and **never places the call**.

2. **Explicit Tenant-Wide DND Scope (Never Agent-Specific):**
   * Do-Not-Call is strictly bound by `(tenant_id, phone_e164)`.
   * Opt-outs are **tenant-wide**:
     ```
     Tenant
      ├── Agent A (e.g., Inbound Support)  ──► Caller says "Stop calling"
      ├── Agent B (e.g., Outbound SDR)     ──► BLOCKED
      ├── Agent C (e.g., Appointment Bot) ──► BLOCKED
      └── Campaign X (Bulk Dialing)        ──► BLOCKED
     ```
   * If Agent A receives an opt-out, Agent B, Agent C, and Campaign X are immediately blocked from calling that recipient.

3. **Audit-Preserved DND Soft-Deactivation (No Hard DELETE):**
   * Hard-deleting DND records (`DELETE /api/dnc/{phone}`) creates severe compliance liability if a tenant mistakenly deletes an opt-out.
   * Deactivation uses `active = False` with mandatory audit fields: `removed_by_user_id`, `removed_at`, `removal_reason`, and a mandatory re-consent confirmation checkbox:
     > *"I confirm that this contact has provided new authorization/consent to receive calls."*

4. **Concise Post-Prewarm Recording Disclosure (Zero Legal Bloat in Voice):**
   * The sub-500ms prewarm greeting plays immediately upon pickup (*"Hello! This is Maya with Acme Health. Am I speaking with Alex?"*).
   * Robotic disclaimers are **never** played before the greeting.
   * When enabled, the disclosure script (*"This call may be recorded for quality and training purposes."*) is woven naturally into the agent's **first spoken response turn after the caller speaks**.
   * State/international jurisdictional notes and FTC disclaimers are removed from the voice statement to keep the speech prompt concise and human.

5. **Normalized Data Architecture (No Profile Duplication):**
   * `user_onboarding_surveys` does **not** store `full_name` or `company_name`. Canonical user information resides exclusively in `users.full_name` and `tenants.name`.
   * Onboarding populates initial values into `users` and `tenants`. The survey table strictly records marketing analytics and versioned terms acceptance (`terms_and_telephony_accepted`, `terms_version`, `terms_accepted_at`, `acceptable_use_version`).
   * `terms_and_telephony_accepted` has `server_default=FALSE` in the database and requires an explicit `True` payload from the user.

6. **Strict Separation of Platform Telemetry vs. Tenant Settings:**
   * Onboarding survey answers (acquisition source, business intent, expected call volume) are strictly developer/platform telemetry and are **never displayed** in tenant settings.
   * Tenant settings exclusively render clean, industry-standard account management attributes: Full Name, Email, Workspace Name, Role, KYC Status, and Change Password.

---

## Phase 1: Database Schema & Compliance Migrations

### 1.1 Migration ID: `029_campaign_compliance_and_onboarding.py`
* **Path:** `server/db/migrations/versions/029_campaign_compliance_and_onboarding.py`
* **Down Revision:** `028_bulk_campaign_contacts`

```python
"""Add campaign compliance attestation, agent recording disclosure, normalized onboarding surveys, and audit-preserved DND columns.

Revision ID: 029_campaign_compliance_and_onboarding
Revises: 028_bulk_campaign_contacts
Create Date: 2026-10-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "029_campaign_compliance_and_onboarding"
down_revision: str | None = "028_bulk_campaign_contacts"
branch_labels = None
depends_on = None
```

#### A. Table `campaigns` Legal Attestation Columns
Add columns to `campaigns` to record the tenant's legal representation:
* `consent_confirmed` (`BOOLEAN`, `nullable=False`, `server_default=sa.text('FALSE')`)
* `consent_attestation_version` (`VARCHAR(32)`, `nullable=False`, `server_default='2026-10-v1'`)
* `attested_by_user_id` (`UUID(as_uuid=True)`, `sa.ForeignKey("users.user_id", ondelete="SET NULL")`, `nullable=True`)
* `attested_at` (`TIMESTAMP WITH TIME ZONE`, `nullable=True`)
* `attested_ip` (`VARCHAR(64)`, `nullable=True`)
* `attested_user_agent` (`VARCHAR(255)`, `nullable=True`)

#### B. Table `agents` Recording Disclosure Columns
Add columns to `agents` (mirrored in `saas_voice_config`):
* `recording_disclosure_enabled` (`BOOLEAN`, `nullable=False`, `server_default=sa.text('FALSE')`)
* `recording_disclosure_text` (`VARCHAR(255)`, `nullable=False`, `server_default='This call may be recorded for quality and training purposes.'`)

#### C. Normalized Table `user_onboarding_surveys`
Store platform/developer analytics without duplicating profile columns:
* `id` (`UUID(as_uuid=True)`, primary key, default `uuid.uuid4`)
* `user_id` (`UUID(as_uuid=True)`, `sa.ForeignKey("users.user_id", ondelete="CASCADE")`, `nullable=False`, `unique=True`)
* `tenant_id` (`UUID(as_uuid=True)`, `sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE")`, `nullable=False`)
* `role` (`VARCHAR(64)`, `nullable=False`) — e.g. `founder`, `tech_lead`, `sales_director`, `operations`, `other`
* `referral_source` (`VARCHAR(64)`, `nullable=False`) — e.g. `google`, `twitter_x`, `linkedin`, `colleague`, `youtube`, `other`
* `primary_use_case` (`VARCHAR(64)`, `nullable=False`) — e.g. `inbound_support`, `outbound_sdr`, `appointment_booking`, `reminders`, `custom`
* `estimated_monthly_minutes` (`VARCHAR(32)`, `nullable=False`) — e.g. `under_500`, `500_2500`, `2500_10000`, `10000_plus`
* `terms_and_telephony_accepted` (`BOOLEAN`, `nullable=False`, `server_default=sa.text('FALSE')`)
* `terms_version` (`VARCHAR(32)`, `nullable=False`, `server_default='2026-10-v1'`)
* `acceptable_use_version` (`VARCHAR(32)`, `nullable=False`, `server_default='2026-10-v1'`)
* `terms_accepted_at` (`TIMESTAMP WITH TIME ZONE`, `nullable=False`)
* `created_at` (`TIMESTAMP WITH TIME ZONE`, `nullable=False`, `server_default=sa.text("now()")`)

Indices:
* `ix_user_onboarding_surveys_user_id` on `user_onboarding_surveys(user_id)`
* `ix_user_onboarding_surveys_tenant_id` on `user_onboarding_surveys(tenant_id)`

#### D. Table `dnc_list` Soft Deactivation & Audit Columns
Upgrade `dnc_list` (`server/db/models/phase5_models.py`) with soft deactivation and audit columns:
* `active` (`BOOLEAN`, `nullable=False`, `server_default=sa.text('TRUE')`, `index=True`)
* `source` (`VARCHAR(64)`, `nullable=False`, `server_default='manual'`) — e.g. `"live_call_opt_out"`, `"operator_ui"`, `"bulk_upload"`
* `added_by_user_id` (`UUID(as_uuid=True)`, `sa.ForeignKey("users.user_id", ondelete="SET NULL")`, `nullable=True`)
* `removed_at` (`TIMESTAMP WITH TIME ZONE`, `nullable=True`)
* `removed_by_user_id` (`UUID(as_uuid=True)`, `sa.ForeignKey("users.user_id", ondelete="SET NULL")`, `nullable=True`)
* `removal_reason` (`VARCHAR(255)`, `nullable=True`)
* `reconsent_confirmed` (`BOOLEAN`, `nullable=False`, `server_default=sa.text('FALSE')`)
* Retain unique constraint: `uq_dnc_tenant_phone` on `(tenant_id, phone_e164)`.

---

## Phase 2: Backend APIs, Pre-Dial Authoritative DND & Opt-Out Auto-Enrollment

### 2.1 Campaign Creation Compliance Validation & Audit Trail
* **File:** `server/routes/campaigns.py`
* **Endpoint:** `POST /api/campaigns`
* **Request Schema (`CampaignCreate`):**
  ```python
  class CampaignCreate(BaseModel):
      name: str
      agent_id: str = Field(..., validation_alias=AliasChoices("agentId", "agent_id"))
      description: str | None = None
      default_country: str = Field("US", validation_alias=AliasChoices("defaultCountry", "default_country"))
      concurrency: int = 5
      max_attempts: int | None = Field(None, validation_alias=AliasChoices("maxAttempts", "max_attempts"))
      retry_delay_minutes: int | None = Field(None, validation_alias=AliasChoices("retryDelayMinutes", "retry_delay_minutes"))
      from_e164: str | None = Field(None, validation_alias=AliasChoices("fromE164", "from_e164"))
      contacts: list[dict[str, Any]] = Field(default_factory=list)
      contact_list_id: str | None = Field(None, validation_alias=AliasChoices("contactListId", "contact_list_id"))
      auto_start: bool = Field(False, validation_alias=AliasChoices("autoStart", "auto_start"))
      # Compliance Attestation
      consent_confirmed: bool = Field(..., validation_alias=AliasChoices("consentConfirmed", "consent_confirmed"))
      consent_version: str = Field("2026-10-v1", validation_alias=AliasChoices("consentVersion", "consent_version"))
  ```
* **Validation & Persistence:**
  ```python
  if not body.consent_confirmed:
      raise HTTPException(
          status_code=400,
          detail={
              "error": {
                  "code": "consent_required",
                  "message": "You must confirm that you have obtained required legal consent for these recipient contacts."
              }
          }
      )
  client_ip = _client_ip(request) or "unknown"
  user_agent = (request.headers.get("user-agent") or "unknown")[:255]

  campaign.consent_confirmed = True
  campaign.consent_attestation_version = body.consent_version
  campaign.attested_by_user_id = ctx.user_id
  campaign.attested_at = datetime.now(timezone.utc)
  campaign.attested_ip = client_ip
  campaign.attested_user_agent = user_agent
  ```

### 2.2 Authoritative Pre-Dial DND Filter (Race-Condition Proof)
* **File:** `server/services/saas/campaign_runner.py`
* **Execution Location:** Directly inside `_worker()` **immediately before** invoking `_dial_one()`.
* **Logic:**
  ```python
  # Authoritative tenant-wide check executed at the last possible millisecond
  async with factory() as session:
      dnc_hit = (
          await session.execute(
              select(DncEntry.id)
              .where(
                  DncEntry.tenant_id == principal.tenant_id,
                  DncEntry.phone_e164 == phone,
                  DncEntry.active.is_(True),
              )
              .limit(1)
          )
      ).scalar_one_or_none()

  if dnc_hit:
      logger.info(
          "campaign_runner.dnc_skipped campaign=%s phone=%s tenant=%s",
          campaign_id, phone, principal.tenant_id,
      )
      async with factory() as session:
          row = await session.get(CampaignContact, contact.id)
          att = await session.get(DialAttempt, attempt_id)
          if att:
              att.status = "dnc_skipped"
              att.error = "Excluded by Do-Not-Call (DND) check immediately prior to dial."
          if row:
              row.status = "dnc_excluded"
          await session.commit()
      stats["dnc_skipped"] = stats.get("dnc_skipped", 0) + 1
      continue  # NEVER dial this contact

  # Only dial if DND check cleared
  result = await _dial_one(...)
  ```
* **Single Outbound Dial Protection:**
  * In single-dial outbound endpoints (`server/routes/campaigns.py`, `server/routes/telephony.py`), execute the same authoritative check. If `phone` is active in `dnc_list` for `principal.tenant_id`, reject with HTTP 400:
    `{"error": {"code": "dnc_blocked", "message": "This phone number is on your tenant's Do Not Call (DND) list."}}`.

### 2.3 Automated Live-Call Verbal Opt-Out Auto-Enrollment
* **Files:** `server/call/call_lifecycle_service.py` and `server/call/close_call_executor.py`
* **Trigger:**
  When a live call terminates with `end_reason == "opt_out"` or disposition matches `_OPT_OUT`:
  1. Extract and normalize `caller_phone` (inbound) or `destination_phone` (outbound) to E.164.
  2. Perform an atomic upsert into `dnc_list`. If the record already exists (even if previously deactivated), reactivate it:
     ```python
     from sqlalchemy.dialects.postgresql import insert as pg_insert

     stmt = (
         pg_insert(DncEntry)
         .values(
             id=uuid.uuid4(),
             tenant_id=tenant_id,
             phone_e164=normalized_phone,
             reason="verbal_opt_out_live_call",
             source="live_call_opt_out",
             active=True,
             added_at=datetime.now(timezone.utc),
             removed_at=None,
             removed_by_user_id=None,
             removal_reason=None,
             reconsent_confirmed=False,
         )
         .on_conflict_do_update(
             index_elements=["tenant_id", "phone_e164"],
             set_={
                 "active": True,
                 "reason": "verbal_opt_out_live_call",
                 "source": "live_call_opt_out",
                 "added_at": datetime.now(timezone.utc),
                 "removed_at": None,
                 "removed_by_user_id": None,
                 "removal_reason": None,
                 "reconsent_confirmed": False,
             },
         )
     )
     await session.execute(stmt)
     await session.commit()
     logger.info("[DNC] Tenant-wide auto-enrollment for %s (tenant %s) on verbal opt-out", normalized_phone, tenant_id)
     ```

### 2.4 DND Soft-Deactivation & Registry Management API
* **File:** `server/routes/campaigns.py`
* **Endpoints:**
  1. `GET /api/dnc`:
     * Query parameters: `status` (`"active"` default, `"inactive"`, or `"all"`), `search`, `page`, `limit`.
     * Returns paginated entries including `active`, `source`, `added_at`, `removed_at`, `removal_reason`.
  2. `POST /api/dnc`: Add single number or reactivate:
     ```python
     class DncAddBody(BaseModel):
         phoneE164: str
         reason: str | None = "manual_operator"
     ```
  3. `POST /api/dnc/bulk`: Bulk import an array of E.164 numbers (upsert `active=True`).
  4. `POST /api/dnc/{phone_e164}/deactivate`:
     * Safe replacement for hard DELETE.
     * Request Schema:
       ```python
       class DncDeactivateBody(BaseModel):
           removalReason: str = Field(..., min_length=5, description="Reason for removing contact from DND list")
           reconsentConfirmed: bool = Field(..., description="Must explicitly confirm new recipient authorization")
       ```
     * Logic:
       ```python
       if not body.reconsentConfirmed:
           raise HTTPException(
               status_code=400,
               detail={"error": {"code": "reconsent_required", "message": "You must confirm that this contact has provided new authorization to receive calls."}}
           )
       entry = await session.execute(
           select(DncEntry).where(DncEntry.tenant_id == ctx.tenant_id, DncEntry.phone_e164 == phone_e164)
       )
       row = entry.scalar_one_or_none()
       if not row:
           raise HTTPException(status_code=404, detail="DND entry not found")
       row.active = False
       row.removed_at = datetime.now(timezone.utc)
       row.removed_by_user_id = ctx.user_id
       row.removal_reason = body.removalReason
       row.reconsent_confirmed = True
       await session.commit()
       ```

### 2.5 Normalized Onboarding Survey API
* **File:** `server/routes/app_auth.py`
* **Endpoints:**
  1. `POST /api/auth/onboarding-survey`:
     ```python
     class OnboardingSurveyBody(BaseModel):
         fullName: str = Field(..., min_length=2)
         companyName: str = Field(..., min_length=2)
         role: str
         referralSource: str
         primaryUseCase: str
         estimatedMonthlyMinutes: str
         termsAccepted: bool = Field(..., alias="termsAccepted")
         termsVersion: str = Field("2026-10-v1", alias="termsVersion")
         acceptableUseVersion: str = Field("2026-10-v1", alias="acceptableUseVersion")
     ```
     * Logic:
       ```python
       if not body.termsAccepted:
           raise HTTPException(
               status_code=400,
               detail={"error": {"code": "terms_required", "message": "You must accept the Terms of Service and Telephony Acceptable Use Policy."}}
           )
       # 1. Update canonical profile records (source of truth)
       user = await session.get(User, ctx.user_id)
       if user:
           user.full_name = body.fullName.strip()
       tenant = await session.get(Tenant, ctx.tenant_id)
       if tenant:
           tenant.name = body.companyName.strip()

       # 2. Persist telemetry to user_onboarding_surveys (no duplicate name columns)
       survey = UserOnboardingSurvey(
           user_id=ctx.user_id,
           tenant_id=ctx.tenant_id,
           role=body.role,
           referral_source=body.referralSource,
           primary_use_case=body.primaryUseCase,
           estimated_monthly_minutes=body.estimatedMonthlyMinutes,
           terms_and_telephony_accepted=True,
           terms_version=body.termsVersion,
           acceptable_use_version=body.acceptableUseVersion,
           terms_accepted_at=datetime.now(timezone.utc),
       )
       session.add(survey)
       await session.commit()
       ```
  2. `GET /api/auth/onboarding-survey`: Checks if survey exists for `ctx.user_id`.
  3. Include `hasCompletedOnboarding: bool` in `POST /api/auth/login`, `POST /api/auth/verify-email-otp`, and `GET /api/auth/me`.

---

## Phase 3: Agent Voice Behavior & Post-Prewarm Recording Disclosure

### 3.1 Conversational Timing & Human Speech Cadence
* **Prewarm Greeting:** Plays instantly upon pickup (sub-500ms). Fast, natural, human (e.g. *"Hello! This is Maya with Acme Health. Am I speaking with Alex?"*).
* **Zero Disclaimer in Prewarm:** Never prepend disclosures before greeting introduction. Callers immediately hang up on automated preambles.
* **Turn 1 Placement:** When `recording_disclosure_enabled == True`, the disclosure is woven into the agent's **very first response turn after the caller speaks**.

### 3.2 Script Compiler & Turn Policy Generation
* **Files:** `server/brain/agent_script_compiler.py` and `server/prompts/agent_voice_rules.py`
* **Clean Instruction (No Jurisdictional Bloat in Voice Prompt):**
  ```python
  def build_recording_disclosure_instruction(disclosure_text: str, language: str) -> str:
      clean_text = disclosure_text.strip() or "This call may be recorded for quality and training purposes."
      return (
          f"\n\n### RECORDING DISCLOSURE POLICY (FIRST RESPONSE TURN ONLY):\n"
          f"Recording disclosure is ENABLED.\n"
          f"In your very first response turn after the caller speaks in response to your greeting, "
          f"you must naturally state the recording disclosure along with your answer or acknowledgment:\n"
          f"\"{clean_text}\"\n"
          f"- Deliver it smoothly and conversationally (e.g., 'Got it! Just so you know, this call may be recorded for quality and training. Regarding your consultation...').\n"
          f"- Do NOT repeat this statement in any subsequent turns.\n"
      )
  ```
* **Telugu Localization (`te-IN`):**
  `"నాణ్యత మరియు శిక్షణ ప్రయోజనాల కోసం ఈ కాల్ రికార్డ్ చేయబడవచ్చు."`

---

## Phase 4: Frontend UI / UX Implementation (`voxly-ai`)

### 4.1 Reusable `CampaignComplianceModal.jsx`
* **File:** `voxly-ai/src/console/ui/CampaignComplianceModal.jsx`
* **Shared Component:** Invoked by both `CampaignsModule.jsx` (Global Campaigns) and `AgentDialBulkPanel.jsx` (`Calls` → `Outbound` in Agent Studio).
* **UI Content:**
  * Header: Shield icon + `"Campaign Compliance Confirmation"`
  * Body:
    > "I confirm that I have the necessary authorization/consent to contact the phone numbers used in this campaign and that my campaign complies with applicable laws and regulations."  
    >  
    > "I understand that I am responsible for the contacts, purpose, content, and legality of the calls made through Voxly."
  * Checkbox: `[ ] I confirm and accept`
  * Action Buttons:
    * `Cancel` (secondary, closes modal)
    * `Confirm & Launch Campaign` (primary, disabled until checked)
  * Clarifying Note: *"Notice: Voxly provides automated telephony infrastructure and does not verify or guarantee the legal validity of your contact lists. You are making this representation as the operating tenant."*

### 4.2 Agent Studio Outbound & Bulk Dialing Alignment
* **File:** `voxly-ai/src/console/modules/agent-workspace/AgentDialBulkPanel.jsx`
* **Location in UI:** Inside `AgentStudioModule` under `Calls` tab → `Outbound` sub-tab.
* **Enhancement:**
  * Clean tab switch: `"Single Call"` vs. `"Bulk Campaign"`.
  * Launching bulk campaign opens `CampaignComplianceModal`.
  * On confirmation, passes `consentConfirmed: true, consentVersion: '2026-10-v1'` to `api.campaigns.create()`.
  * Displays immediate feedback if contacts are scrubbed by DND: `"3 numbers on your tenant Do Not Call list were excluded."`

### 4.3 Agent Recording Disclosure Settings Card
* **File:** `voxly-ai/src/console/modules/agent-workspace/AgentSettingsPanel.jsx`
* **UI Elements:**
  * Title: **Call Recording & Disclosure**
  * Toggle: `Enable recording disclosure` (`[ OFF / ON ]`, default `OFF`)
  * When switched `ON`:
    * Field: `Disclosure script:`
    * Textarea: Default pre-filled with `"This call may be recorded for quality and training purposes."`
    * Description: *"The agent will naturally deliver this disclosure during its first response turn after the caller speaks."*
    * Clean, simple disclosure focus without long jurisdictional legal warnings.

### 4.4 Clean Tenant Settings View (Strict Isolation of Telemetry)
* **File:** `voxly-ai/src/console/modules/SettingsModule.jsx`
* **Rule:** **Never display marketing survey answers in tenant settings.**
* **Tenant Cards Displayed:**
  1. **Profile & Account:** Owner / Full Name (editable), Work Email (read-only verified), Role.
  2. **Organization:** Company / Workspace Name (editable), Workspace ID, Created Date.
  3. **Security:** "Change Password" dialog (connecting to `POST /api/auth/change-password`).
  4. **Identity Verification:** KYC status badge.
  5. **Wallet & Usage:** Remaining minutes and balance.

### 4.5 Post-Auth Onboarding Survey Modal
* **File:** `voxly-ai/src/components/OnboardingSurveyModal.jsx`
* **Trigger:** Intercepts user immediately after first signup/login if `user.hasCompletedOnboarding === false`.
* **Flow:**
  * **Step 1: Your Role & Business:** Full Name, Company Name, Role dropdown.
  * **Step 2: Platform Strategy:** Referral source, primary objective, estimated monthly minutes.
  * **Step 3: Terms & Acceptable Use:**
    * Mandatory checkbox: *"I agree to the Terms of Service, Privacy Policy, and Anti-Spam / Telephony Acceptable Use Policy."*
    * Checkbox starts unchecked (`termsAccepted: false`).
    * Submit button is disabled until checked.
  * Submits to `POST /api/auth/onboarding-survey`, updates local auth context, and reveals console.

### 4.6 DND Registry Management Screen with Deactivation Audit Modal
* **File:** `voxly-ai/src/console/modules/CampaignsModule.jsx` (DND sub-tab)
* **Features:**
  * Tabbed view: `Active DND` vs. `Deactivated / Audit History`.
  * Table: Phone Number, Source (`Live Call Opt-Out`, `Manual`), Date Added, Removal Reason, Deactivated At.
  * `"Add to Do Not Call"` button (modal for single E.164 or bulk paste).
  * `"Deactivate / Remove"` action per row:
    * Opens modal with mandatory fields:
      * Removal Reason input (e.g. *"Recipient requested re-subscription via web form"*).
      * Checkbox: `[ ] I confirm that this contact has provided new authorization to receive calls.`
      * Confirm button calls `POST /api/dnc/{phoneE164}/deactivate`.

### 4.7 API Client Updates (`voxly-ai/src/services/api.js`)
```javascript
export const api = {
  ...
  dnc: {
    async list(params) {
      return await api.request('GET', `/api/dnc?${new URLSearchParams(params || '')}`);
    },
    async add(phoneE164, reason) {
      return await api.request('POST', '/api/dnc', { phoneE164, reason });
    },
    async bulkAdd(phones, reason) {
      return await api.request('POST', '/api/dnc/bulk', { phones, reason });
    },
    async deactivate(phoneE164, removalReason, reconsentConfirmed) {
      return await api.request('POST', `/api/dnc/${encodeURIComponent(phoneE164)}/deactivate`, {
        removalReason,
        reconsentConfirmed
      });
    },
  },
  auth: {
    ...
    async submitOnboardingSurvey(data) {
      return await api.request('POST', '/api/auth/onboarding-survey', data);
    },
    async getOnboardingSurvey() {
      return await api.request('GET', '/api/auth/onboarding-survey');
    },
  }
};
```

---

## Phase 5: Verification, Reticle & Pytest

### 5.1 Reticle In-App Browser Verification (`voxly-ai`)
Use Reticle MCP tools (`reticle_session`, `reticle_act_and_wait`, `reticle_assert`) to drive the running Vite app and assert UI behavior:
1. **Flow 1: Campaign Compliance Modal (Global & Agent Console):**
   * Open Campaign wizard → Advance to Review → Assert "Launch" button is disabled.
   * Click attestation checkbox → Assert button becomes enabled.
   * Click Launch → `reticle_assert` campaign creates and modal dismisses.
2. **Flow 2: Agent Recording Disclosure Toggle:**
   * Open Agent Studio → Settings tab → Toggle `Enable recording disclosure` to `ON`.
   * Assert textarea displays default text without legal bloat.
   * Save → `reticle_assert` persistence upon reload.
3. **Flow 3: Onboarding Survey Intercept & Clean Settings:**
   * Simulate user with `hasCompletedOnboarding = false`.
   * Verify terms checkbox is unchecked by default and blocks submission.
   * Check terms → Submit → Assert console unlocks.
   * Navigate to Settings page → `reticle_assert` Profile displays Full Name and Workspace Name, but **no** marketing survey questions are visible.
4. **Flow 4: DND Registry & Deactivation Audit Modal:**
   * Open DND tab → Add `+15550198888` → Verify active row.
   * Click Deactivate → Assert confirm button disabled until reason and re-consent checkbox are provided.
   * Complete modal → Confirm → `reticle_assert` row moves to Deactivated history with audit metadata.

### 5.2 Backend Automated Testing (`server/tests/test_compliance_dnc_and_onboarding.py`)
* `test_campaign_creation_fails_without_consent_attestation`: Assert HTTP 400.
* `test_campaign_creation_stores_audit_trail`: Assert IP, version, and timestamp stored.
* `test_authoritative_pre_dial_dnd_skips_blacklisted_contact`: In `campaign_runner.py`, add phone to DND after campaign creation; assert runner skips dialing and marks `dnc_excluded`.
* `test_tenant_wide_dnd_blocks_all_agents`: Confirm DND entry added via Agent A blocks dials from Agent B and Agent C.
* `test_live_call_verbal_opt_out_auto_populates_dnc`: Simulate call end with `end_reason="opt_out"`; assert phone exists with `active=True`.
* `test_dnc_deactivation_requires_reconsent_and_preserves_audit`: Deactivate number; verify `active=False`, `removal_reason`, and `reconsent_confirmed=True`.
* `test_onboarding_survey_updates_canonical_profiles_and_requires_terms`: Verify `users.full_name` and `tenants.name` update, survey terms default is false, and survey telemetry saves cleanly.

---

## Complete Verification & Sign-off Checklist

| Requirement | Scope | Target File | Verification Metric |
| :--- | :--- | :--- | :--- |
| Alembic Migration 029 | Database | `server/db/migrations/versions/029_*.py` | Executes cleanly up and down |
| Compliance Attestation API | Backend | `server/routes/campaigns.py` | `POST /api/campaigns` requires `consentConfirmed` |
| Authoritative Pre-Dial DND Filter | Backend | `server/services/saas/campaign_runner.py` | Authoritative check right before `_dial_one` |
| Tenant-Wide DND Enforcement | Backend | `server/db/models/phase5_models.py` | Unique on `(tenant_id, phone_e164)` |
| Live Call Opt-Out Auto-Enrollment | Backend | `server/call/close_call_executor.py` | Upserts `dnc_list` on `end_reason="opt_out"` |
| DND Soft-Deactivation API | Backend | `server/routes/campaigns.py` | `POST /api/dnc/{phone}/deactivate` audits removal |
| Post-Prewarm Voice Disclosure | Brain | `server/brain/agent_script_compiler.py` | Woven into first response turn after caller speaks |
| Compliance Modal Component | Frontend | `voxly-ai/src/console/ui/CampaignComplianceModal.jsx` | Renders in both Campaign & Outbound tabs |
| Clean Recording Disclosure Card | Frontend | `voxly-ai/src/console/modules/agent-workspace/AgentSettingsPanel.jsx` | Clean toggle + script without legal bloat |
| Clean Settings Module | Frontend | `voxly-ai/src/console/modules/SettingsModule.jsx` | Zero survey telemetry leakage; clean profile |
| Normalized Onboarding Survey Modal | Frontend | `voxly-ai/src/components/OnboardingSurveyModal.jsx` | Terms unchecked by default; canonical updates |
| DND Registry Management Tab | Frontend | `voxly-ai/src/console/modules/CampaignsModule.jsx` | Active & Audit tabs with Deactivation modal |
| Reticle & Pytest Suite | QA | `server/tests/test_compliance_dnc_and_onboarding.py` | All tests pass, zero regressions |
