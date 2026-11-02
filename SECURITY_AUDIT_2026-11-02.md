# Security audit and fixes — 2 November 2026

A review of the customer site and console (`dialtact-app/`), the admin panel (`web/`) and
the API (`server/`): sign-in, the admin login, every API and websocket route, and the
browser side. Earlier audits (`SECURITY_AUDIT_AND_REMEDIATION.md`,
`AUDIT_REPORT_AUTH_TENANT_MARKETING.md`) were read first; this covers what was still open.

## Fixed

### Critical
| Issue | Fix |
|---|---|
| `/ws/stt-realtime` and `/ws/tts` had no authentication: anyone could use the platform's speech providers for free, or write audio into another tenant's call recording. | Authenticated before the socket is accepted (subscriber token in a subprotocol/header, or an admin session); a subscriber may only use its own tenant's live call; per-user rate and concurrency limits. `server/routes/ws.py` |
| `POST /api/voice/stt-brain` ran speech-to-text and the LLM with any prompt, unauthenticated. | Removed (nothing called it). |
| Admin panel on Next 15.5.27, inside the range of an unauthenticated remote-code-execution advisory (GHSA-2464-fhr4-w9xw). | Upgraded to 15.5.28. |

### High
| Issue | Fix |
|---|---|
| Account takeover via Google sign-in: someone could pre-register a victim's address, and when the victim later signed in with Google the squatter's password kept working. | Google sign-in on an unverified account voids its password and ends its sessions. `auth_service.login_or_create_oauth_user` |
| The 6-digit email code could be brute-forced (no attempt limit; changing the email's case reset the limit). | 5 attempts per address per 15 minutes, keyed on the normalised address; then the code is burned and a new one is needed. |
| Support or billing admins could become platform admin by impersonating or resetting a platform admin. | Platform admins can't be impersonated or have their password reset; the `/api/admin` API refuses impersonated sessions. |
| The SMTP "test connection" sent the stored SMTP password to any host in the request. | The stored password is used only for the stored host, port and user; TLS required; generic errors. |
| Admin login brute force (case changes reset the limit; no lockout). | Normalised limiter key; 10 failures lock the account for 15 minutes (shared through Redis); sign-ins audited. |
| Unauthenticated writes to runtime/Test Studio settings, and reads of any agent's full prompt (`/api/prompt/effective`), call history, metrics. | Admin session or tenant-scoped instruction access required. |

### Medium
- **Google sign-in:**
  - Login CSRF: the sign-in state is now tied to the browser that started it with an HttpOnly cookie.
  - Removed the legacy link that accepted a raw access token.
  - State and handoffs are kept in Redis, so a callback can land on any worker.
- **Signing secrets:** the server refuses to start outside development with a default or short `SESSION_SECRET`/`JWT_SECRET`, and signatures are compared in constant time.
- **Sign-in limits:** per-account limits on login, password-reset and verification emails, keyed by the normalised address, so rotating IPs doesn't buy more guesses.
- **Rate limiter:** it no longer locks everyone out when its table fills.
- **Reset links:** only the newest one works, and a reset spends all of them. Disabled accounts can't get a session from an email code, a reset or Google.
- **Cookies:** refresh and admin cookies are `Secure` whenever the request is HTTPS, including the public dev site.
- **Call scoping:**
  - `/api/tts` and `/api/voice/turn` only touch the caller's own calls and sessions.
  - The call-metrics and call-prompt endpoints check the tenant.
- **Telnyx:**
  - Recording download is restricted to Telnyx hosts, never follows redirects, has a size cap, and sends the API key only to Telnyx.
  - Unsigned webhooks are refused outside development.
- **Vobiz:** webhooks no longer take the master token from the URL, and replayed nonces are rejected through Redis.
- **Generation limits:** each tenant gets 10 calls per 5 minutes on the LLM generation endpoints.
- **Admin environment-keys page:** changes are audited by field name, URLs must be https, and the environment and webhook URLs need super_admin.
- **Admin panel:**
  - The admin-only API check ignores requests that came through the Cloudflare tunnel, and a percent-encoded path (`/api/%64ev/…`) no longer slips past the Vite guard.
  - Next.js middleware fails closed and uses the right cookie name.
  - The login open redirect is fixed.
  - Logout is POST only.
- **Public site security headers** (dev server and production build):
  - On every response: no framing (clickjacking on `/signin`), nosniff, referrer and permissions policies, and HSTS over HTTPS.
  - A Content-Security-Policy allowing only this app, Google Sign-In and Razorpay. Checked in Chrome against a production build with no violations, and the 3D mascot, glow cursor and Google button all work.
- **API responses:** HSTS added; `localhost` CORS origins are allowed in development only.

### Low
- **Links from server data:** links the server supplies (checkout, KYC, compliance sources, debug reset) must be http(s), so a `javascript:` link is never followed.
- **KYC tab:** it can no longer redirect the console (reverse tabnabbing).
- **Access token:** it's no longer read from `localStorage`.
- **Error and health responses:** they no longer return raw exception text or the storage bucket name. Email addresses are masked in auth logs.
- **Vendor endpoints:** the provider and vendor catalog is admin-only.
- **Web-agent socket:** it no longer accepts a token in the URL.
- **Duplicate setting:** removed the duplicate `AUTH_DEBUG_EXPOSE_RESET_TOKEN=true` line from `.env` (the later `false` was the one in effect).

## Redis
- **Rate limits:** `server/utils/rate_limiter.py` is shared through Redis, so every worker and server counts against the same limit and a restart doesn't reset it. The limit is applied atomically by a single script on the Redis server. If Redis is unreachable it falls back to in-process counting, and reconnects in the background so no request waits on it.
- **Public price catalog:** `/api/billing/catalog` is cached for 30 s (`server/utils/cache.py`). Saving rates, tax settings, pricing tags or a tier price clears it.
- **Also in Redis:** Google sign-in state and handoffs, the admin login lockout, and Vobiz webhook nonces.

## Still open
1. **No two-factor login for admins** (TOTP for admin accounts and the platform-admin emails). It's the single most valuable next step.
2. **`SESSION_SECRET` in `.env` is 24 characters.** Rotate it to a random 48+ character value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Every admin and legacy session is signed out once.
3. **The Vite dev server is published at `app-dev.dialtact.com`** (unminified source, the live-reload socket). Point that hostname at the production build, or put Cloudflare Access in front of it.
4. **Access tokens can't be revoked before they expire** (up to their 15-minute default life). Add a per-user `tokens_valid_after`.
5. **Sign-up reveals that an address is registered** (409 `email_taken`), and password-reset timing differs slightly.
6. **Behind a proxy (Railway/Docker), the API needs `--proxy-headers --forwarded-allow-ips`.** Without it every visitor shares one IP for rate limiting.
7. **Admin environment keys** are stored unencrypted in `data/dev_secrets.json`.
8. **The legacy vanilla UI in `client/` and some `scripts/*.py` probes** call routes that now need an admin session.
9. **`npm audit` in `dialtact-app` reports `follow-redirects`** (Node-only, not in the browser bundle).
