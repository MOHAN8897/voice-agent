# Tenant phone-service onboarding

Implemented against Vobiz's published subaccount and hosted KYC documentation,
reviewed on 2026-10-21. No live subaccount, real document verification, or paid
number order was created during development.

## Flow

1. A signed-in workspace billing administrator with a verified email opens
   **Settings → Phone service verification**, or begins a number purchase.
   Number purchase first shows current provider inventory and the admin's
   retail monthly price. Selecting a number retains the country, number and
   target agent in session storage scoped to the signed-in tenant and user.
2. The server creates one `customer_use` subaccount for that tenant using the
   parent's credentials. Entity type and legal name are locked after creation.
3. The one-time child token is encrypted with a dedicated Fernet key and bound
   to the tenant UUID. No child credentials are sent to the browser.
4. The server creates a redirect session for Vobiz's hosted KYC widget. Vobiz
   collects the entity-specific documents. The hosted URL is encrypted in the
   database and reused while the current session remains valid. A failed
   verification gets a fresh session so documents can be submitted again.
5. The callback at `/api/webhooks/voice-kyc` verifies `X-Vobiz-Signature` as
   HMAC-SHA256 over the exact raw body with the parent's auth token. Its account
   and session must match persisted state. A callback only triggers a fresh
   status lookup; it never approves a tenant from callback/redirect fields.
   Callbacks are optional: local deployments without a public HTTPS callback
   poll status instead. The server never submits an insecure callback URL.
6. Purchases and PSTN calls require Vobiz's current `kyc_calls_blocked=false`
   and an enabled, active subaccount belonging to the configured parent.
   Provider outages deny access temporarily. Browser practice remains ungated.
7. Before buying a DID, the child gets its own default inbound application with
   this platform's answer/hangup/fallback URLs. The DID is purchased directly
   with child credentials; Vobiz documents that the parent is still billed.
8. Number ownership, carrier selection and carrier resource IDs are persisted.
   Calls, hangups, signed callbacks and CDR reconciliation use that owning
   account. New tenant calls never fall back to parent credentials.
9. Returning from hosted verification restores the selected-number review.
   The user must explicitly confirm the purchase after approval. Inventory,
   the admin price and funds are checked again; verification does not reserve
   a number or trigger a charge. Closing the dialog clears the saved choice.

## Restart and failure handling

- Database rows are retained across restarts. No boot path recreates accounts
  or overwrites their credentials, KYC, number ownership or selected provider.
- An ambiguous account-creation result is `provisioning_unknown`, and a lost
  one-time token is `credentials_lost`. Both need support reconciliation; the
  system deliberately does not create another account or use the parent token.
- HTTP purchase/account/session POSTs are not automatically replayed. A number
  purchase first reconciles the same child's owned-number list.
- Interrupted provision jobs are reclaimed after ten minutes. Failed retries
  eventually become `needs_attention`; paid/uncertain reservations remain held.
  They are not refunded or offered to another customer while provider ownership
  is unresolved. Jobs without a recorded provider need manual reconciliation.
- Customer-owned numbers cannot be reassigned just by changing a database
  tenant ID. Release uses the child account and never puts its number into our
  parent inventory. A pending release retains ownership; teardown cannot move
  past carrier release until confirmation is available.

## Didit and Admin Dev Portal Integration

Vobiz's documented telecom onboarding does not require a Didit account or a
second Didit verification. This integration uses Vobiz KYC for Vobiz phone
service. Didit remains a separate, optional platform identity workflow.
Other carriers retain the existing `KYC_GATE_PURCHASES` policy when Didit is
configured. Keeping/removing that separate policy is a product decision; a
Vobiz KYC result is not an assertion of compliance for every other platform use.

### Admin Verification Queue & Cockpit Shift
Platform administrators inspect and manage tenant verification via `/api/dev/admin/kyc`
and the Dev Portal's Compliance panel (`web/components/admin/panels/VerificationPanel.tsx`).
1. **Unified Ingestion**: The queue unifies both `list_voice_verifications()` (Vobiz
   child subaccounts) and `kyc_service.list_verifications()` (Didit sessions), placing
   active carrier voice KYC records at the top of the queue with explicit provider badges.
2. **Normalized Status Transitions**: The admin override endpoint (`admin_set_voice_kyc_status`)
   accepts standard statuses (`"Approved"`, `"Declined"`, `"In Review"`), automatically
   normalizing them to internal database tokens (`"verified"`, `"failed"`, `"pending"`).
3. **Audit Trails**: All status overrides enforce a minimum 8-character justification statement
   and are persisted to admin audit logs.
4. **Tenant Detail Cockpit**: The tenant compliance view (`web/app/dev/(portal)/admin/tenants/[tenantId]/page.tsx`)
   provides a dedicated Voice KYC card showing real-time calling gate pass state (`ENABLED` vs `BLOCKED`),
   entity type, subaccount Auth ID, and verified document status (PAN, Aadhaar, GST).

## Deployment

This change authors migration `040_vobiz_tenant_subaccounts`; it does not apply
it to a live database or alter production settings.

1. Back up the database and configure a stable, dedicated
   `VOBIZ_SUBACCOUNT_ENCRYPTION_KEY` in the secret manager. Generate a Fernet
   key once. Share the same key across API/worker processes and restarts; keep
   a recoverable backup. Do not regenerate it at startup or rotate without
   re-encrypting the existing rows.
2. Configure the parent's Vobiz credentials, the exact `VOXLY_FRONTEND_URL`,
   and a public HTTPS API base for live callbacks. If a callback is configured,
   it must be reachable over HTTPS. Status polling works without a callback.
3. Apply `alembic -c alembic.ini upgrade head` through the normal deployment
   process, then deploy API and workers together. The upgrade is additive.
   Downgrading removes encrypted credentials/session state; a code rollback
   should retain this table until all carrier resources are reconciled.
4. Complete onboarding using a designated staging tenant and its authorized
   documents. Confirm KYC, buy one permitted DID, verify inbound/outbound and
   CDR accounting. Offline tests do not replace this provider acceptance check.

Existing parent-owned numbers remain explicitly legacy/platform scoped; this
migration does not transfer them. Moving them to a child requires deliberate
provider reconciliation and routing configuration. Vobiz's unassignment rules
include a 15-day cool-off after recent calls. Do not rewrite ownership fields
or automatically move live customer numbers to another tenant.

Vobiz test-mode KYC endpoints update account KYC state. They are never selected
automatically and must not be used against a real tenant to simulate approval.

## Sources

- [Vobiz onboarding and direct child purchases](https://www.vobiz.ai/docs/sub-accounts/onboarding-flow)
- [Hosted KYC session](https://www.vobiz.ai/docs/sub-accounts/kyc/kyc-session)
- [KYC status](https://www.vobiz.ai/docs/sub-accounts/kyc/kyc-status)
- [Webhook events and HMAC](https://www.vobiz.ai/docs/sub-accounts/kyc/email-flow-webhook)
- [Default inbound application](https://www.vobiz.ai/docs/applications/update-application)
- [Didit identity workflows](https://docs.didit.me/getting-started/introduction)
