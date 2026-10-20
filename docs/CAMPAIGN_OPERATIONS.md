# Primary campaign operations

This change covers the Gemini Live / Vobiz calling path. Secondary calling
stacks were not part of the functional audit. No production database, calling
account, billing rate or deployment was changed during this work.

## Deployment requirements

1. Back up the database and apply Alembic revision
   `041_campaign_execution_safety`, after revision `040_vobiz_tenant_subaccounts`,
   through the normal deployment procedure. Apply the additive schema before
   starting the updated API or worker. Migration tests exercised generated
   schemas on an isolated PostgreSQL container; each deployed database must
   still be upgraded and checked separately.
2. API and campaign workers must share PostgreSQL and a real Redis 6.2 or newer
   instance. Stream-token consumption uses `GETDEL`, and metadata updates use
   Redis transactions. Redis failure rejects media authentication in staging
   and production. The local fake cache is only for development and tests.
3. Run the worker with the existing entry point, `python -m worker.main`.
   API instances also recover durable campaigns. Both paths use the same
   database leases, so a missed notification does not discard a campaign.
4. Drain WebSocket connections during deployment. Media sessions and prewarm
   objects live on the process that owns the socket. Shared admission prevents
   duplicate sessions; it does not move an active conversation between hosts.
5. Budget database connections across all API and worker processes:
   process count times (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) must fit the database
   connection budget. Add worker instances only with measured database and
   upstream capacity. There was no production load benchmark in this audit.

After applying migrations, run `python -m scripts.verify_postgres` before
serving the new release. This read-only command compares the database revision
with the code's required Alembic heads and exits with an error on a mismatch.
It does not seed records. Database connectivity alone does not prove the schema
is current: revision 039 is missing the phone number fields added by 040 and
the campaign fields added by 041, causing both console list requests to fail.

## Admission and pacing

`server/services/saas/call_admission.py` reserves a tenant call slot in a
transaction under a tenant row lock, before contacting the carrier. Ringing,
accepted, answered and uncertain requests hold capacity. A linked internal
call is not counted a second time.

Request IDs are tenant scoped. Repeating the same request returns its recorded
result. Reusing its ID with different settings returns a conflict. Concurrent
requests to the same tenant/destination are rejected while a request is active.

`SAAS_MAX_OUTBOUND_CPS` defaults to 1. The effective tenant limit is bounded by
that ceiling and `Tenant.limits.max_outbound_cps`. The effective concurrent
call limit is bounded by the platform and tenant limits, with a hard ceiling
of 20 in this implementation. These are application limits, not purchased
carrier capacity. Keep them within the actual calling account allocation.
Where several tenants share an upstream account or quota, budget their
aggregate traffic separately; the admission ledger is tenant scoped.

CPS limits initiation speed independently of concurrent channels. See the
[Vobiz pacing guidance](https://www.vobiz.ai/docs/faq/cps). The campaign runner
uses bounded batches and the shared admission check repeats the pacing check
across simultaneous campaigns and API requests.

## Recovery, pause and uncertain calls

- Campaign runs have 120-second execution leases. Recovery polls every 10
  seconds, in batches of at most 100 runs. Each tick reloads the actor's current
  account access and calling consent.
- Pause and cancel stop new contact claims. Work already handed to the carrier
  can continue. Confirm the call has ended before making a replacement call.
- Retry delay and maximum attempts apply to confirmed nonconnections. A POST
  timeout, server error or malformed success is not proof that no call exists.
  Such requests retain their slot and are never automatically redialed.
- A verified end callback releases the admission record. Stale ambiguous
  attempts become `requires_review`. Reconcile them against the provider's call
  history and verified internal call records. Do not delete reservations or
  force a redial because a local HTTP request timed out. Automated carrier
  reconciliation and a privileged reconciliation UI are not included here.
- Calling windows use a recipient's supplied IANA timezone, or the campaign
  fallback timezone. Invalid timezone data cannot authorize an out-of-window
  call. The DNC check repeats immediately before dialing and cannot be disabled
  by an untrusted client.
- Tenant status and the configured inbound wallet gate run before inbound
  transfer routing or AI media setup. This work does not certify all costs or
  concurrency accounting for externally transferred carrier legs.

## Contact import and tenant UI

One shared setup page contains campaign details, contact source and mapping,
validation, and a review panel with explicit calling authorization. Advanced
settings are collapsed. The agent workspace bulk action uses the same page.
The dashboard applies the server campaign status and coalesces statistics
requests, with no more than four in flight per view, including effect remounts.

CSV and XLSX imports are limited to 5 MB, 100 columns and 10,000 rows; XLSX
expanded content is also bounded. Only 50 rows are previewed, while all accepted
rows are validated and sent. Saved lists and legacy oversized lists cannot
bypass the campaign batch limit. Missing script variables must be reviewed,
skipped or given explicit fallback values before launch.

Map the CSV name column to `full_name` and use `{{contact.full_name}}` in the
script. First and last names are optional. Existing `{{name}}`,
`{{customer_name}}`, `{{lead_name}}` and legacy caller-name tags remain
supported. Additional columns map to `custom_fields.<key>` and are available
as `{{contact.custom_fields.<key>}}`. Map each destination field once; duplicate
destinations are rejected rather than overwriting a recipient's data.

Only placeholders present in the script become script variables. Details
collected during a call are plain instructions, not required CSV fields.
`{{contact.full_name | there}}` supplies an explicit fallback. Unsupported or
unclosed placeholders block launch. The review shows sample recipients and
their rendered business script, without platform instructions. Upload, paste
and saved-list inputs use the same server validation. Saving separate mapping
templates and contact lists is no longer part of campaign setup.

Create, import and start all validate required fields on the server. Campaigns
retain their published script version in `schedule.script_version`; primary
call preparation and prewarm look it up through the tenant-owned campaign.
Publishing a newer agent script does not silently change a campaign already
prepared with an older version. A republish between preflight and creation
requires the user to check contacts again.

## Security and verification limits

The local evidence is in `.gravitas/sessions/campaign-platform-audit/` and the
ignored scanner outputs in `.gravitas/security-reports/`. It includes tenant
isolation, concurrent admission, replay, timeout, DNC, upload limits, failed
wallet checks, metadata races, and responsive browser tests. Browser campaign
tests use synthetic intercepted APIs and never dial real numbers.

Semgrep, Bandit, production dependency audits and local OWASP ZAP scans were
run. The ZAP baseline retained an informational non-storable-content warning:
private responses intentionally use `no-store`. Active API scanning also
reported HTTP-only transport and unavailable-service responses from the
deliberately unconfigured target. Its eight SQL-injection heuristics were
replayed and returned identical denied/unavailable responses; there was no
database behind this scan. Authenticated staging scanning remains required.

Strix did not produce an assessment. Its Gemini 3.8 preflight timed out; a
discovery-listed 2.5 recovery model was rejected as unavailable to this account.
Neither attempt is a penetration-test pass. No staging URL was provided, so
production HTTPS, deployed headers, production permissions, real call quality,
carrier callbacks and sustained load were not verified.

By explicit user decision, workspace deletion keeps its existing authenticated
owner plus confirmation-word behavior. Password/email-code reauthentication
was proposed and declined; the deletion contract and dialog were not changed.

## Public indexing

The public Vite build prerenders six public pages with distinct titles and
canonical URLs. Public links use paths, the sitemap lists public pages, and
authenticated console/admin surfaces are marked `noindex`. Public content is
available in generated HTML before JavaScript. Unknown public routes are not
rewritten to an indexable home-page success response by the Vercel config.
Follow [Google's JavaScript SEO guidance](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics).
These are technical indexing improvements; they do not guarantee rankings.
