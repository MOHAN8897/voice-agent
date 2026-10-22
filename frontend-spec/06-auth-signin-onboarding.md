# 06 — Sign-in, auth, and onboarding

**Code today**

| Route | File |
|-------|------|
| `/app/login` | `web/app/app/(auth)/login/page.tsx` |
| `/dev/login` | `web/app/dev/(auth)/login/page.tsx` |
| Auth layout | `(auth)/layout.tsx` + `AuthShell` |
| Tenant | `/app/select-tenant` |
| Access denied | `/app/access-denied` |
| Form | `web/components/auth/LoginForm.tsx` |
| Logout | `LogoutButton` → `/api/app/logout` or `/api/dev/logout` |

**PRD:** `prd/11` §4 Authentication; `prd/13` sessions/CSRF; `prd/17` multi-tenant.

Stitch “login” / “split hero form” maps to `AuthShell` (already a two-pane layout). Restyle the aside from Stitch; keep the form contract.

## Business sign-in (`/app/login`)

### Layout

- **Left (lg+):** Brand, eyebrow “Business Console”, headline, three ticks (8-section brain, Test Studio, call outcomes), footer line Telugu + PSTN.
- **Right:** form card.

Dev variant uses “Restricted access” copy — never used on the public site.

### Form elements

| Element | Behavior |
|---------|----------|
| Title | “Sign in” |
| Subtitle | “Access your agents, calls, and Test Studio.” |
| Username | text, required, autocomplete username |
| Password | password, required |
| Submit | Primary button, loading “Signing in…” |
| Error | `FieldError` from API `j.error.message` |
| Session check | On mount `refreshPortalSession("app")` → redirect `next` |
| CSRF | Store `csrf_token` from login JSON |

Endpoint: `POST /api/app/login` body `{ username, password }`, `credentials: include`.

Query: `?next=/app/agents` (must start with `/`). `?error=` from middleware.

**Stitch extras to add if the frame has them:**

- “Forgot password” — **gap** (only add when API exists)
- Google/SSO — **gap** (do not fake buttons)
- Sign up / Create workspace — **gap**; until then CTA: “Request access” mailto or waitlist

Do not add a public self-serve signup that creates tenants without a backend.

## Dev sign-in (`/dev/login`)

Same `LoginForm` with `endpoint="/api/dev/login"`, `redirectTo="/dev"`, `portalKind="dev"`.

Visual: AuthShell `variant="dev"`. Copy must say authorized staff only.

## Tenant selector (`/app/select-tenant`)

After login, if multiple tenants: list of workspace cards (name, id mono, role). Cookie `tenant_id`.

**Today:** mock Default + Staging. Target: `GET /api/auth/session` tenant list only.

Empty: “No workspace yet” + contact admin.  
Error: retry.  
Escape: “Sign in with a different account” → login.

## Access denied (`/app/access-denied`)

Explain missing permission. Links: Overview (if any role), Sign out. Never show the forbidden resource body.

## Session UX

- Cookie session + CSRF header on mutations (`auth-client.ts`)
- 401 → redirect to the matching login with `next`
- Console footer: Profile + Sign out

## First-run onboarding (gap — required to sell)

After first successful `/app` login with zero agents:

1. **Welcome** — “Create your first voice agent”  
2. **Name + language** — te-IN default; en-IN / hi-IN available (`prd/17`)  
3. **Paste brief or skip** — compiles Business Brain  
4. **Play greeting / Test Studio**  
5. **Optional:** assign PSTN number (`prd/17` first-time auto-assign)

Checklist on Overview until: agent exists, brain Identity saved, one test call completed.

Do not force name-collection in the **agent script**; that’s a voice-policy rule, not an onboarding field.

## Sign-up (future)

When product enables it:

- Email + password or invite token
- Org name → tenant
- Agree to Terms + recording consent
- Land on onboarding wizard

Until API exists, Stitch “Create account” screens stay **out of production nav**.
