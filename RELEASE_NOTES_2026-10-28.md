# Voice platform and landing-page update — 28 October 2026

Branch: `working-app-22-10-2026`.

This update brings together the pending voice reliability, workspace, billing, administration, and marketing changes. It preserves the configured voice-tier stacks and the landing hero. It does not migrate customer data, change production configuration, or publish existing customer agents automatically.

## Landing page

- Replaced the long sequence of repeated feature sections with seven focused sections: recorded voice previews, a workspace preview, calling workflows, setup, wallet pricing, FAQ, and a closing call to action.
- Preserved the hero component, hero content, mascot implementation, and hero props. A source comparison verified all three invariants.
- Added a workspace image captured from the actual console using fictional contact data, clearly labelled as an example.
- Added selectable sales, support, and campaign workflows, accessible native FAQ controls, mobile layouts, keyboard focus treatment, and consistent section spacing/card surfaces.
- Reused existing recorded industry audio. Playback has loading, stop, completion, and error/retry handling, with no autoplay.
- Replaced the obsolete monthly/annual plan selector with wallet/tier information and the real billing entry point. Marketing no longer changes a workspace's tier through that selector.
- Simplified the footer. Removed a newsletter form that reported success without persisting a subscription, and show social links only when configured.
- Updated navigation and removed unconditional booking/automatic-follow-up claims from the active below-hero copy. Supported integrations and confirmed actions remain prerequisites.
- Corrected a marketing-copy guard that confused a CSS `30%` gradient stop with an unsourced performance claim; regression coverage retains detection of actual unsupported claims.

The structure draws on the demo-first presentation, concrete workflows, and setup/product explanations used by [Retell](https://www.retellai.com/), [Vapi](https://vapi.ai/), and [Bolna](https://www.bolna.ai/), reviewed on 28 October 2026. No competitor design assets, customer logos, testimonials, performance figures, or certification claims were copied.

## Conversation and speech reliability

- Unified Gnani v3.0 tag guidance and the final speech contract around its documented 13-tag catalog. Cues remain optional and contextual; ordinary pauses use punctuation.
- Preserved queued audio tails and EOS ordering across synthesis turns. Empty error lists are harmless; recoverable errors retain the warm socket, while fatal credential/credit errors still stop it.
- Replaced a fixed synthesis wait with an inactivity deadline that allows continuing audio progress. Explicit documented Hinglish routing is preserved; this does not introduce a new console language across all stacks.
- Handled completed-empty Sarvam speech without replaying the entire compiled brain. Approved endings use the platform farewell; open turns use bounded same-model clarification, then the existing locale recovery on failure.
- Preserved terminal usage accounting on incomplete SSE responses. The selected conversations model remains unchanged.
- Distinguished future interest/deferral from rejection in semantic closing, rejected malformed/conflicting close outputs, and retained the server as the farewell and hangup authority.
- Removed conflicting JSON/speech-text closing instructions and unsupported team/callback promises from generation templates.
- Preserved provider hangup attempts during the expected teardown/finalization handoff, with regression coverage for lifecycle outcomes.

Provider-empty replies can still occur, and occasional unnecessary follow-up questions remain a model-quality limitation. Recovery is not a claim that these provider behaviors have disappeared. A genuine first-class Hinglish product option and human listening QA remain separate work.

## Agent workspace, CRM, and tags

- Added Objection & Objective Handling with rule type, enabled state, multiline guidance, and available actions. Only enabled guidance enters the model context; editor metadata is excluded.
- Rule edits use draft revision checks, preview, compilation, and publication. Explicitly empty rule lists stay empty after reload, and approved free-form FAQ notes are retained.
- Added one floating save action for unsaved agent changes, improved script/settings layouts and categories, persistent sidebar collapse, and voice-filter availability counts.
- Improved the lead pipeline with server filters, counts, pagination, ownership, notes, call history, campaign handoff, and tenant-confirmed conversion.
- Enforced lead write permissions for mutation routes and read-only controls for viewers. Added row locking, stale-edit rejection, explicit note clearing/unassignment, and safer automatic contact matching.
- Prevented unrelated identity-less calls from merging, preserved tenant-maintained contact names, and made automatic call replays idempotent. A planned visit alone no longer creates a confirmed meeting stage.
- Preserved Unicode custom tags, excluded obvious contact/URL/markup data, made normalization idempotent, and reconciled contradictory sentiment, rejection, and follow-up tags.
- Aligned browser sign-in routing and session presentation with the configured six-hour inactivity window. Routing tests now wait for sign-in completion and use the actual sidebar control before checking settings.

Callback requests remain a managed follow-up list; they do not automatically schedule a future redial. Bookings and other external actions require an enabled integration and a successful result.

## Wallet, tax, and administration

- Persisted per-stack browser-agent pricing alongside phone pricing and used channel-appropriate quotes in test-call entry points.
- Improved GST configuration and checkout terms, tax-inclusive wallet credit handling, verified payment recovery, refund reversal, idempotency/locking, and protection against duplicate payment attempts.
- Preserved pending captured payments for verification instead of inviting another charge. Required renewed review when a tax quote changes and ignored stale amount quotes.
- Consolidated administration navigation, tenant/user entry points, overview analytics, and voice-stack configuration. Retired duplicate legacy configuration entry points.
- Added evidence-based voice-profile readiness checks and protected credential references. Enabled but unavailable tiers remain visible with clear admission limits.
- Improved backend-request timeout/error presentation without discarding the workspace session or saved edits.

## Verification

Verification performed against the final source changes:

- 486 changed-file backend tests passed; 3 skipped.
- 41 browser tests passed, including seven landing tests and the existing script, lead, wallet, routing, and layout flows.
- Seven Node tests passed for copy guards, rule round-trip, and script parsing.
- Vite production build/prerender and the Next.js production build passed. Next's repository configuration skips lint/type checking during its build; that build is not a separate TypeScript-check claim.
- Semgrep SAST, source secret-pattern checks, and `git diff --check` were run before committing. The local verification report records their final results and Reticle verdicts.

Earlier live verification used three fictional generated agents across English, Telugu, and Hindi, plus six live speech-synthesis requests and same-model recovery probes. These were simulated conversations/provider probes, not real customer PSTN calls. No claim is made that every language, OAuth connection, provider, carrier, or production concurrency condition was retested.

Deploy backend and frontend through the normal release process. Review/regenerate scripts produced by older templates and publish updated agent configurations to refresh saved brains; active calls retain their existing session context.

Raw call logs, local recordings, customer screenshots, browser episodes, build output, local environment files, and temporary execution files are excluded from publication. Review notes and the fictional public workspace preview are included.
