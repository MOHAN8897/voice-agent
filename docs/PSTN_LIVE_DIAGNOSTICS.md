# Private live PSTN diagnostics

`GET /api/dev/telephony/diagnostics?call_id=<internal UUID or carrier call ID>&after=0&limit=100`

Use the existing authenticated Dev Portal session cookie. The endpoint requires
`dev.stack.read` (administrator, developer or platform administrator). App-session
cookies are not accepted. Do not put credentials in the URL. Responses are
`private, no-store`. Unknown call IDs return 404 rather than another call's data.

The response contains a cursor-pollable `timeline` and current `media` counters,
configured/negotiated codec, rate and channels. Poll once per second, passing the
returned `next_cursor` as `after`. `limit` is 1–300. Omitting `call_id` selects the
most recently updated timeline; once selected, poll an explicit ID from `ids`.

Timelines merge internal and carrier IDs when the lifecycle binds them. Collection
continues when console `LOG_PSTN` logging is disabled. An allowlist excludes
transcripts, prompts, phone numbers, URLs, tokens and raw exception messages.
These diagnostics use no network or disk I/O on the media event loop.

Retention is process-local: 100 recent calls, 300 events per call, cleared on
restart. An advanced `oldest_cursor` can indicate that older events were evicted.
For multiple API workers, query the worker that owns the call (sticky routing);
this endpoint is not a durable cross-worker audit store. Existing call archives
and the authenticated `/api/dev/telephony/forensics` endpoint support post-call review.

Useful events:

- `prewarm.adopt_timeout`: greeting preparation exceeded the answer-time wait.
- `greeting.deferred.miss`: no usable prepared opening.
- `greeting.fallback.requested`: live opening response explicitly requested.
- `greeting.pickup.recovery`: caller's hello arrived before any agent audio.
- `media.out.first` / `media.out.progress`: successful server sends.
- `media.out.playout_gap`: over 200 ms late with queued audio; investigate blocking
  work or transport latency.
- `media.out.socket_lost`: send failure or timeout, including exception type and
  close code when available. The bridge ends the unusable call.
- `media.out.silent`: no initial audio within the startup grace period.
- `stream.disconnected`: carrier WebSocket close code.

Sent frames prove server transport, not handset audibility. Compare them with the
carrier recording. A failed send must not report healthy outbound transport.

The first-audio watchdog applies to outbound calls with a greeting enabled;
intentional greeting suppression and diagnostic test modes are excluded.
Audio sends have a two-second deadline. Failure hangups have a four-second budget.

Run the focused regressions with:

```powershell
.venv/Scripts/python.exe -m pytest server/tests/test_pstn_live_diagnostics.py -q
```
