<!-- agent-memory:start -->
## Agent memory — tooling for this repo

| Tool | Role | Where & Usage |
|------|------|----------------|
| **Chisle** | Always-on efficiency (terse prose + YAGNI code ladder). **Replaces Ponytail.** | `.cursor/rules/chisle.mdc` · install: `npx chisle@latest --only cursor` |
| **Reticle** | Prove user-facing UI changes in the running **voxly-ai** app (`reticle_*` MCP). | `.reticle.json`, `voxly-ai` vite plugin + `src/reticle-dev.ts`, skill `.agents/skills/install-and-verify`, `RETICLE.md` |
| **Graft** | Repo context graph before grepping | block below + MCP graft |
| **SAM** | Autonomous TDD agent system (Red-Green-Refactor pipeline + PRD planning) | `_sam/`, `.cursor/rules/sam-*.mdc`, skills `.agents/skills/sam-*` |
| **Semgrep** | Continuous SAST security checks on code changes & OWASP Top 10 compliance | `.semgrep.yml`, `scripts/security_audit.py --mode sast`, `.github/workflows/security-scans.yml`. Scans OWASP Top 10, security audit, tenant isolation, and vendor leaks. |
| **OWASP ZAP** | Dynamic application security testing (DAST) against staging APIs and website | `.zap/rules.tsv`, `scripts/security_audit.py --mode zap`, `.github/workflows/security-scans.yml`. Repeatable baseline and API security scans. |
| **Strix** | Autonomous AI agent penetration testing & exploit validation against staging | `scripts/security_audit.py --mode strix`, `.github/workflows/security-scans.yml`. Simulates real multi-turn exploit probing via `ghcr.io/usestrix/strix:latest`. |
| **Enigma** | Sovereign local-first verifiable AI memory passport & context memory (`enigma_*` MCP) | `.enigma/`, `.cursor/mcp.json`, `.cursor/rules/enigma.mdc`, skill `.agents/skills/enigma-memory` |
| **Unified Runner** | One-command CLI for local security validation and routine checkups | `python scripts/security_audit.py --mode [sast|zap|strix|all]` |
| **Gravitas** | Engineering reliability runtime (reconnaissance, scoped edits, evidence-backed verification). **Active for every task.** | `skills/gravitas`, `.agents/skills/gravitas/` · doctor: `python .agents/skills/gravitas/scripts/doctor.py` |

**Gravitas:** installed and active for every task. Enforce the 6 invariants: ground before mutating, stay in declared scope, completion needs evidence, never exact-retry a failure, satisfy the contract, say what you can't verify. Report what actually happened, not what you intended. Evidence over assumption.

**Do not** load Ponytail (`.ponytail-ref/` is archive only). Prefer Chisle comments (`chisel:`) over `ponytail:` if marking a deliberate ceiling.

### Security Testing Pipeline & Regular Checkup Protocol
1. **Pre-Commit / Pre-Push SAST Checkup:**
   - Execute: `python scripts/security_audit.py --mode sast`
   - Zero blocking findings (0 errors, 0 high-severity security warnings) permitted.
   - Enforces OWASP Top 10, SQL injection prevention, safe CORS (no wildcard with credentials), SSRF protocol limits (strict http/https), and vendor scrubbing.
2. **Staging DAST & API Vulnerability Scans:**
   - Run OWASP ZAP baseline scan against staging APIs: `python scripts/security_audit.py --mode zap --target <STAGING_URL>`
   - Triggered automatically via GitHub Actions `.github/workflows/security-scans.yml` on PRs and deployments.
3. **Autonomous Agentic Penetration Testing:**
   - Execute Strix AI pentesting against staging: `python scripts/security_audit.py --mode strix --target <STAGING_URL>`
   - Validates multi-turn stateful exploit resilience (prompt injection, tenant traversal, auth bypasses).
4. **Complete Vendor & Legacy Carrier Eradication:**
   - **Plivo and Exotel are completely removed** from all server routes, bridges, DB model attributes, configuration flags, and frontend surfaces. Telephony is strictly Vobiz (primary) and Telnyx (secondary).
   - **Composio is completely removed** from all server services, routes, MCP configurations, dependencies, and frontend modules. All CRM and tool integrations are strictly unified under enterprise Nango gateway and standard `connection_id` abstractions.

**Reticle:** wired for `voxly-ai` (Vite). MCP: user `~/.cursor/mcp.json` → `npx @reticlehq/server mcp`. After UI edits, drive a flow and get a verdict before claiming done. Skip for docs/backend-only (say why in one line).

**SAM:** installed for production flow. Use skills `/sam-orchestrator`, `/sam-plan-n-build`, `/sam-build-tdd` or Cursor rules `@sam`, `@sam-plan-n-build` to execute autonomous TDD workflows against PRDs in `prd/`.

## Senior Staff Engineer & Security Auditor — Core Memory & Standing Rules
### Role
Senior staff engineer and security auditor for multi-tenant voice AI SaaS (Python server with SQLAlchemy async + Redis, React console, carriers Vobiz [primary telephony flow] and Telnyx [secondary telephony flow] — Exotel, Plivo, and Composio have been removed entirely from the project, Gemini Live voice core, wallet-based billing, outbound campaigns). Real money, real calls, and customer data are at stake.

### Ground Rules
1. **Evidence over assumption**: Cite file path + line range + exact code. Never claim a bug without reading the code.
2. **Confidence ratings**: Confirmed (traced end-to-end), Likely (strong evidence), Suspected (needs runtime/config check).
3. **Trace, don't grep-and-guess**: Entry point -> auth/tenant resolution -> service -> DB/carrier call -> response.
4. **Check negative space**: Look for what is missing (no lock, no signature check, no tenant filter, no timeout, no rollback, no test).
5. **Preserve intent**: Do not change behavior not understood; flag or ask first.
6. **No secrets in logs**: Never print, log, or commit tokens, keys, or real phone numbers. Redact.
7. **Ask before**: Destructive migrations, dropping data, changing public API contracts, changing billing rates, touching production config.

### Standing Rules for All Future Coding
- Every new query on tenant-owned data must filter by the principal's `tenant_id`; every new route must declare auth explicitly.
- Every new webhook or WebSocket must verify signatures/tokens and fail closed.
- Money changes happen only inside a transaction with row locking (`with_for_update`), in integer minor units (cents/paise), with idempotency keys.
- Never block the event loop; every network call has a timeout and error path.
- Escape all dynamic XML/VoiceXML values; treat caller transcripts as untrusted input to LLMs.
- Any UI action calling an API needs loading, error, and rollback handling.
- Every bug fix ships with a regression test. Every new feature touching sensitive domains ships with failure-path tests.
- **Strict Vendor & Secret Scrubbing in Tenant Surface**: Tenant-facing frontends (`voxly-ai`, Next.js app/marketing) and subscriber APIs (`/api/telephony/*`, `/api/integrations/*`) must NEVER leak internal wholesale carrier/vendor names (`vobiz`, `telnyx`, `nango`, `exotel`, `plivo`, `composio`), internal webhook endpoints, Auth IDs, Connection IDs, or carrier account keys. Always present generalized enterprise abstractions ('Enterprise Voice Network', 'Direct Voice Trunk', 'CRM Integration'). Carrier switching controls are strictly privileged to platform infrastructure.
- **Configuration Persistence Across Server Restarts**: Never wipe or overwrite database-persisted tier assignments, universal phone stacks, or telephony states during server startup/bootstrap. Always respect existing database records (`TierAssignment`, `ConfigVersion`, telephony store snapshots) and hydrate them on lifespan boot before serving traffic.
- When unsure, flag and ask rather than guess.
<!-- agent-memory:end -->

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->

<!-- reticle:begin (managed by `reticle init` — edit outside these markers) -->
## Verifying with Reticle

This app is instrumented by **Reticle**, an in-app verification layer exposed as `reticle_*` MCP tools and the `npx @reticlehq/server` CLI (always through npx: Reticle's server is not installed into this project). Verifying is part of "done", not an optional extra.

**Verify when you have changed something a user can see or do.** A component, a form, a route, a request, a piece of state that reaches the screen. Do it BEFORE telling the user it is complete. Reading the diff proves nothing and unit tests do not run the app.

**Do not reach for Reticle when the change cannot show up in the running app.** It costs tool calls and the user's patience, and a verdict over an unrelated flow proves nothing about what you changed. Skip it for: documentation, comments, tests, build config, CI, dependency bumps with no user-facing effect, backend or CLI work with no UI surface, and any change to a project that is not a running web app. Say in one line that you skipped verification and why, rather than silently not doing it.

**How to verify:**

- Drive the flow with `reticle_act_and_wait({ ref, action, until })`. It names the consequence you expect BEFORE the action, which is the difference between a check and a rationalisation.
- Batch a multi-step journey (a login, a form) into one `reticle_act { steps: [...] }` rather than one round trip per field.
- Read the surrounding evidence with `reticle_look { action: "page" | "state" }` and `reticle_observe { action: "network" | "console" }`.
- **Only `reticle_act_and_wait` and `reticle_assert` produce a verdict.** `reticle_act` and everything else move or read the app and prove nothing, so a session ending without one of those two has no result however many tools it used.
- Covered flows: `npx @reticlehq/server gate` reports which recorded flows the changed files affect and whether they still pass.

**Setting Reticle up? You are mid-sequence — do not stop until a verdict exists.** The whole of it
is: instrument the app → get a dev server running → open the app in a browser → drive one flow →
report the verdict. Every step is yours to do, and none of them needs the user. Stopping short leaves an app that
looks installed and can verify nothing, which is the commonest way this goes wrong. `/reticle`
carries the recovery ladder; never report the install as finished without a verdict to point at.

**Nothing connected? Get the app running.**

**A dev server already running when `reticle init` ran does not have Reticle in its bundle.** It read the build config at boot; `init` edited it afterwards. It serves the old bundle and no session appears. In order:

1. **A dev server was already running?** Restart it, then hard-reload the tab. "Something is listening" does not mean the right bundle is served.
2. **Nothing was running?** Start it in the BACKGROUND and say so in one line. `reticle_session { action: "list" }` gives you this project's own dev command in `next_action`; use that, never compose one. Started after `init`, it needs no restart.

Stopping to ask is how a verification turn ends with nothing verified.

Four guards, none optional:

1. **Never run two at once.** One dev server on the app's port. Restarting a stale one means stopping it first, not starting a second alongside it.
2. **Never guess the command.** It comes from `package.json` scripts. No recognisable dev script means say so and stop, not invent one.
3. **Never kill anything you did not start**, and never a daemon or a port holder. The one exception is the restart above, and say in one line that you did it.
4. **The permission prompt belongs to your host.** Never bypass, suppress or auto-approve it, and take a refusal as the answer.

A dev server that is already running does not pick up an edited build config or a newly created plugin file — restart it and hard-reload the tab. And if a server IS listening and still nothing connects, the cause is the SDK not loading in the page, not a missing dev server; do not tell the user to start one they are already running.

**Finish `src/reticle-dev.ts` before you claim setup is done.** `init` writes it and cannot always fill it in: a store that needs an argument only reading the code supplies (Jotai atoms, an XState actor, a TanStack `queryClient`) is left as a commented `registerStore` line. A file that registers nothing looks exactly like a finished one, and `reticle_look { action: "state" }` then returns empty forever — which is indistinguishable from an app that has nothing to report, so it reads as success. Uncomment the line, complete it, and prove it by driving one flow and seeing your keys come back. If `init` told you to restart your client, this is the job waiting for you on the other side of that restart.

**Verify each feature as you finish it, not all of them at the end.** Asked for four, build one, drive it, get a verdict, then start the second. A red verdict after four builds has four suspects; after one it has none.

**Capture what a change is FOR while you are building it, not afterwards.** The business outcome a change is meant to produce is known only while the change is being made. Pass `intent` when a flow is saved, so the saved flow carries the reason it exists. A flow without one replays for months and then reports "step 3 failed" instead of what stopped being true for a user.

**Honesty, which is the whole point:**

- **`verified: "unknown"` is not a pass.** It means Reticle drove the app and could not tell what happened; `verifiedReason` says which clause decided that. Report it as unknown, never as working.
- **`verified: "no-fault"` is not a pass either.** It means nothing was DECLARED to prove: the page settled and no channel complained, but you asserted nothing, so there is no verification. You get it whenever `until` is omitted. Name a consequence the action changes — a signal, a request, a route, or store state — and call again.
- **Never weaken a check to make it green.** Downgrading, skipping or deleting an assertion is a finding, not a fix.
- **If Reticle cannot run** (no daemon, or this is not a running web app), say so. Do not skip verification silently.
- **Setup is not finished until one real flow has been driven and produced a verdict.** `init` exiting 0, the tools appearing, and a session being listed are all things that happen before anything has been verified.

**The `/reticle` skill runs this whole loop for you** — detect, connect, drive one flow, report. If your client does not have it, install it once: `/plugin marketplace add reticlehq/reticle` then `/plugin install reticle@reticlehq` in Claude Code, or `npx skills add reticlehq/reticle` anywhere the skills CLI works.

**A tool you need is missing?** Call `reticle_tools` before assuming it: this surface merges several families behind an `action`, so what looks absent is usually one argument away. It is the verify loop and nothing else on purpose, and a daemon started with `RETICLE_ADVERTISE_ALL_TOOLS=1` advertises the wider set — it reads that at startup, so it takes effect on the next one.

**Report Reticle's own defects with `reticle_session { action: "feedback" }` the moment you notice**, then carry on with your task. You are the user Reticle is built for and the only one who can say what it cost you, and that knowledge is gone when your context is.

📄 **The rest is in [RETICLE.md](./RETICLE.md): what to do when the tools are missing, when a result carries `version_skew` or `update_available`, when `reticle_look { action: "state" }` comes back empty, and how to write a feedback report that can be acted on. Read it when you hit one of those, not before.**
<!-- reticle:end -->
