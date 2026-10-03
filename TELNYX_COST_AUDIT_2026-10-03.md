# Telnyx Cost & Call Volume Audit

**Account:** Telnyx (production credential from `.env` → `TELNYX_API_KEY`)
**Tenancy:** Connection `3041007474451679060` ("Voice Agent Dev"), TN `+13526146416` (DID, US), outbound profile `3040713087544985585`
**Billing window audited:** `2026-09-25T00:00:00Z` → `2026-10-04T00:00:00Z`
**Report date:** 2026-10-03
**Data source:** Live Telnyx API v2 (`/v2/usage_reports`, `/v2/recordings`, `/v2/balance`, `/v2/phone_numbers`)
**Currency:** USD

---

## 1. Executive summary

| Metric | Value |
|---|---|
| Calls **attempted** since 25 Sep | **68** |
| Calls **connected / completed** | **48** |
| Connect rate | **70.6 %** |
| Failed attempts (no charge) | 20 (29.4 %) |
| Total talk time | 3,256.8 s = **54.28 min** |
| Voice minutes **billed** by Telnyx | **79 min** |
| **Total Telnyx spend since 25 Sep** | **$3.3657** |
| **Average cost per connected call** | **$0.0701** |
| Average cost per *attempted* call | $0.0495 |
| Effective cost per **talk** minute | **$0.0620** |
| Effective cost per **billed** minute | **$0.0426** |
| **Account balance remaining** | **$0.56** ⚠️ |

**Three findings need action now:**

1. **Balance is $0.56.** At the observed burn rate this is **less than one day** of traffic before outbound calls start failing at the carrier. Oct 1 already shows 7 attempts / 0 connections.
2. **Your internal cost model under-prices SIP trunking by ~74 %.** `usage_pricing.py` assumes `$0.009/min` for India; Telnyx actually bills a flat **`$0.0351/min`**. Your books under-record true cost by **~$0.0025 per call → 3.76× understatement on a per-talk-minute basis**.
3. **Recording is metered on both call legs**, so you pay recording for ~1.66× your actual talk time. Your model bills a flat `$0.002/min` on talk time and does not model this.

---

## 2. Costing per minute — actual rates

Rates derived directly from Telnyx `usage_reports` cost ÷ billed seconds. All rates are **exactly constant** across every one of the 19 billing days in September, so these are contractual, not estimated.

| Telnyx product | What it is | **Rate (USD/min)** | Rate/hr | Share of spend |
|---|---|---:|---:|---:|
| `sip-trunking` | US → India PSTN origination | **$0.03510** | $2.106 | **82.4 %** |
| `recording` | Call recording storage | $0.00200 | $0.12 | 7.7 % |
| `media-streaming` | Media Streaming (websocket) | $0.00354 | $0.213 | 5.2 % |
| `call-control` | Voice API call control | $0.00200 | $0.12 | 4.7 % |
| **Total** | | | | **$3.3657** |

### Blended rates

| Basis | Rate |
|---|---|
| **Per talk minute** (54.28 min real conversation) | **$0.06201 / min** |
| **Per Telnyx-billed voice minute** (79 min) | **$0.04260 / min** |

> The two differ by 45 % purely because of how Telnyx rounds billing — see §5.

### Route attributes confirmed by Telnyx

| Dimension | Value |
|---|---|
| `direction` | `outbound` (100 %) |
| `country_iso` / `country_code` | `IN` / `91` |
| `source_country_code` | `1` (US) |
| `tn_type` | `DID` |
| `connection_type` | `call-control-authentication` |
| `short_duration_call` | `false` for all 48 |
| `streaming_type` | `websocket` |

**100 % of spend is US → India (country code 91) on one DID.** There is no route diversity — a single carrier rate card governs 100 % of cost.

---

## 3. Call volume since 25 September 2026

### 3.1 Daily

| Date | Attempted | Connected | Failed | Talk sec | Billed min | Spend |
|---|---:|---:|---:|---:|---:|---:|
| 2026-09-25 | 11 | 9 | 2 | 718 | 17 | **$0.7296** |
| 2026-09-26 | 0 | 0 | 0 | 0 | 0 | $0.0000 |
| 2026-09-27 | 19 | 16 | 3 | 1,130 | 28 | **$1.1907** |
| 2026-09-28 | 12 | 8 | 4 | 440 | 11 | **$0.4687** |
| 2026-09-29 | 19 | 15 | 4 | 965 | 23 | **$0.9767** |
| 2026-09-30 | 0 | 0 | 0 | 0 | 0 | $0.0000 |
| 2026-10-01 | 7 | **0** | **7** | 0 | 0 | $0.0000 |
| 2026-10-02 | 0 | 0 | 0 | 0 | 0 | $0.0000 |
| 2026-10-03 | 0 | 0 | 0 | 0 | 0 | $0.0000 |
| **Total** | **68** | **48** | **20** | **3,253** | **79** | **$3.3657** |

Traffic is **bursty and weekday-clustered**: 4 of 10 days carry all volume, and there has been **no traffic at all since 1 Oct**. Sep 26/30 and all of Oct 2–3 are zero.

### 3.2 Connection outcomes (`hangup_details`)

| Hangup detail | Attempted | Connected | Connect % | Spend | Meaning |
|---|---:|---:|---:|---:|---|
| `send_bye` | 28 | 28 | **100 %** | $1.4391 | We hang up cleanly |
| `recv_bye` | 29 | 20 | 69.0 % | $1.3338 | Remote hangs up; 9 attempts never answered |
| `send_cancel` | 4 | 0 | 0 % | $0.0000 | Cancelled before answer |
| `recv_refuse` | 7 | 0 | 0 % | $0.0000 | **Remote explicitly refused** |
| **Total** | **68** | **48** | 70.6 % | **$2.7729** | |

**20 of 68 attempts (29.4 %) never connect and correctly cost $0.** That part is healthy — Telnyx is not charging you for failed dials. But a **29.4 % connect failure rate** is a product-level problem worth chasing, and the 7 `recv_refuse` on 1 Oct (with zero connections) look like a deliberate test-block or a reputation/SIM issue.

### 3.3 Call duration distribution

| Statistic | Value |
|---|---|
| Min | 10.50 s |
| p25 | 46.44 s |
| **Median** | **69.02 s** |
| p75 | 83.16 s |
| Max | 155.10 s |
| **Mean** | **67.85 s** |

| Bucket | Calls | % |
|---|---:|---:|
| < 30 s | 4 | 8.3 % |
| 30–60 s | 18 | 37.5 % |
| ≥ 60 s | 26 | 54.2 % |

**45.8 % of connected calls are under 60 seconds** — and because of Telnyx's per-call rounding (§5), a 10-second call is charged as a full minute. This is where money leaks.

### 3.4 Destinations

| Destination | Calls | % |
|---|---:|---:|
| `+918897908470` | 32 | 66.7 % |
| `+919398247132` | 15 | 31.3 % |
| `+919618474960` | 1 | 2.1 % |
| **Total** | **48** | |

Three numbers, all Indian mobile (`+91 8…`/`+91 9…`). Effectively **single-customer test traffic**.

---

## 4. Cost per call — the numbers you asked for

### 4.1 Headline averages

| Metric | Value |
|---|---|
| Average cost per connected call | **$0.0701** |
| — of which SIP trunking | $0.0578 (82.4 %) |
| — of which recording | $0.0054 |
| — of which media streaming | $0.0036 |
| — of which Voice API (call-control) | $0.0033 |
| Average cost per *attempted* call | $0.0495 |
| Average billed minutes per call | 1.646 |
| Average talk time per call | 67.85 s (1.131 min) |

### 4.2 Cost by call length — the rounding penalty is visible

| Billed min | Calls | SIP cost | All-in cost |
|---:|---:|---:|---:|
| 1 | 22 | $0.0371 | ~$0.041 |
| 2 | 21 | $0.0702 | ~$0.084 |
| 3 | 5 | $0.1053 | ~$0.129 |
| **Total** | **48** | **$2.7729** | **$3.3676** |

A 10.5 s call and a 59 s call both cost $0.0371 of SIP. **The cheapest calls are the most expensive per second.**

### 4.3 Full per-call ledger (all 48 calls)

Model reproduces Telnyx's actual invoice to **0.06 %** ($3.3676 modelled vs $3.3657 actual). Recording is modelled at per-call `ceil(Σ leg duration)`. Media Streaming is allocated pro-rata by talk time.

| # | Date | Start (UTC) | Destination | Talk s | Voice billed min | Voice+API $ | Recording $ | Media $ | All-in $ |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | 2026-09-25 | 2026-09-25T08:30:35 | +918897908470 | 107.54 | 2 | 0.0742 | 0.0080 | 0.0058 | 0.0880 |
| 2 | 2026-09-25 | 2026-09-25T09:40:54 | +918897908470 | 67.56 | 2 | 0.0742 | 0.0060 | 0.0036 | 0.0838 |
| 3 | 2026-09-25 | 2026-09-25T12:01:44 | +919398247132 | 76.90 | 2 | 0.0742 | 0.0060 | 0.0041 | 0.0843 |
| 4 | 2026-09-25 | 2026-09-25T12:19:38 | +918897908470 | 127.56 | 3 | 0.1113 | 0.0100 | 0.0068 | 0.1281 |
| 5 | 2026-09-25 | 2026-09-25T12:34:18 | +918897908470 | 108.32 | 2 | 0.0742 | 0.0080 | 0.0058 | 0.0880 |
| 6 | 2026-09-25 | 2026-09-25T12:55:25 | +918897908470 | 35.34 | 1 | 0.0371 | 0.0040 | 0.0019 | 0.0430 |
| 7 | 2026-09-25 | 2026-09-25T13:15:01 | +918897908470 | 93.68 | 2 | 0.0742 | 0.0080 | 0.0050 | 0.0872 |
| 8 | 2026-09-25 | 2026-09-25T13:32:23 | +919398247132 | 71.44 | 2 | 0.0742 | 0.0060 | 0.0038 | 0.0840 |
| 9 | 2026-09-25 | 2026-09-25T13:35:19 | +919398247132 | 31.86 | 1 | 0.0371 | 0.0040 | 0.0017 | 0.0428 |
| 10 | 2026-09-27 | 2026-09-27T08:35:07 | +918897908470 | 87.10 | 2 | 0.0742 | 0.0060 | 0.0047 | 0.0849 |
| 11 | 2026-09-27 | 2026-09-27T08:41:54 | +918897908470 | 24.96 | 1 | 0.0371 | 0.0020 | 0.0013 | 0.0404 |
| 12 | 2026-09-27 | 2026-09-27T08:45:24 | +918897908470 | 72.66 | 2 | 0.0742 | 0.0060 | 0.0039 | 0.0841 |
| 13 | 2026-09-27 | 2026-09-27T08:56:25 | +918897908470 | 78.40 | 2 | 0.0742 | 0.0060 | 0.0042 | 0.0844 |
| 14 | 2026-09-27 | 2026-09-27T09:05:10 | +918897908470 | 125.96 | 3 | 0.1113 | 0.0100 | 0.0068 | 0.1281 |
| 15 | 2026-09-27 | 2026-09-27T09:16:53 | +918897908470 | 81.80 | 2 | 0.0742 | 0.0060 | 0.0044 | 0.0846 |
| 16 | 2026-09-27 | 2026-09-27T09:34:18 | +918897908470 | 87.94 | 2 | 0.0742 | 0.0060 | 0.0047 | 0.0849 |
| 17 | 2026-09-27 | 2026-09-27T10:01:26 | +918897908470 | 121.88 | 3 | 0.1113 | 0.0080 | 0.0065 | 0.1258 |
| 18 | 2026-09-27 | 2026-09-27T11:09:09 | +918897908470 | 71.86 | 2 | 0.0742 | 0.0060 | 0.0039 | 0.0841 |
| 19 | 2026-09-27 | 2026-09-27T13:49:30 | +918897908470 | 34.64 | 1 | 0.0371 | 0.0040 | 0.0019 | 0.0430 |
| 20 | 2026-09-27 | 2026-09-27T13:50:48 | +919398247132 | 46.44 | 1 | 0.0371 | 0.0040 | 0.0025 | 0.0436 |
| 21 | 2026-09-27 | 2026-09-27T13:54:10 | +918897908470 | 69.48 | 2 | 0.0742 | 0.0040 | 0.0037 | 0.0839 |
| 22 | 2026-09-27 | 2026-09-27T16:46:29 | +919398247132 | 57.76 | 1 | 0.0371 | 0.0040 | 0.0031 | 0.0442 |
| 23 | 2026-09-27 | 2026-09-27T18:43:34 | +918897908470 | 55.58 | 1 | 0.0371 | 0.0040 | 0.0030 | 0.0441 |
| 24 | 2026-09-27 | 2026-09-27T19:15:01 | +918897908470 | 40.56 | 1 | 0.0371 | 0.0040 | 0.0022 | 0.0433 |
| 25 | 2026-09-27 | 2026-09-27T19:15:54 | +918897908470 | 74.20 | 2 | 0.0742 | 0.0060 | 0.0040 | 0.0842 |
| 26 | 2026-09-28 | 2026-09-28T06:52:55 | +919398247132 | 47.00 | 1 | 0.0371 | 0.0040 | 0.0025 | 0.0436 |
| 27 | 2026-09-28 | 2026-09-28T06:54:08 | +918897908470 | 44.84 | 1 | 0.0371 | 0.0040 | 0.0024 | 0.0435 |
| 28 | 2026-09-28 | 2026-09-28T06:55:23 | +918897908470 | 37.62 | 1 | 0.0371 | 0.0040 | 0.0020 | 0.0431 |
| 29 | 2026-09-28 | 2026-09-28T06:56:42 | +919398247132 | 30.78 | 1 | 0.0371 | 0.0020 | 0.0017 | 0.0408 |
| 30 | 2026-09-28 | 2026-09-28T06:57:43 | +919398247132 | 52.88 | 1 | 0.0371 | 0.0040 | 0.0028 | 0.0439 |
| 31 | 2026-09-28 | 2026-09-28T17:39:59 | +918897908470 | 26.42 | 1 | 0.0371 | 0.0020 | 0.0014 | 0.0405 |
| 32 | 2026-09-28 | 2026-09-28T17:48:30 | +918897908470 | 72.24 | 2 | 0.0742 | 0.0060 | 0.0039 | 0.0841 |
| 33 | 2026-09-28 | 2026-09-28T19:03:08 | +918897908470 | 128.72 | 3 | 0.1113 | 0.0060 | 0.0069 | 0.1282 |
| 34 | 2026-09-29 | 2026-09-29T05:48:48 | +918897908470 | 17.02 | 1 | 0.0371 | 0.0020 | 0.0009 | 0.0400 |
| 35 | 2026-09-29 | 2026-09-29T05:49:18 | +918897908470 | 10.50 | 1 | 0.0371 | 0.0020 | 0.0006 | 0.0397 |
| 36 | 2026-09-29 | 2026-09-29T07:30:48 | +918897908470 | 55.88 | 1 | 0.0371 | 0.0040 | 0.0030 | 0.0441 |
| 37 | 2026-09-29 | 2026-09-29T07:56:05 | +918897908470 | 63.48 | 2 | 0.0742 | 0.0040 | 0.0034 | 0.0836 |
| 38 | 2026-09-29 | 2026-09-29T13:08:35 | +919398247132 | 55.92 | 1 | 0.0371 | 0.0040 | 0.0030 | 0.0441 |
| 39 | 2026-09-29 | 2026-09-29T13:12:55 | +918897908470 | 155.10 | 3 | 0.1113 | 0.0120 | 0.0083 | 0.1316 |
| 40 | 2026-09-29 | 2026-09-29T13:35:35 | +919398247132 | 78.48 | 2 | 0.0742 | 0.0060 | 0.0042 | 0.0844 |
| 41 | 2026-09-29 | 2026-09-29T13:48:23 | +919398247132 | 46.82 | 1 | 0.0371 | 0.0040 | 0.0025 | 0.0436 |
| 42 | 2026-09-29 | 2026-09-29T13:53:35 | +919398247132 | 44.72 | 1 | 0.0371 | 0.0040 | 0.0024 | 0.0435 |
| 43 | 2026-09-29 | 2026-09-29T13:56:30 | +919398247132 | 69.02 | 2 | 0.0742 | 0.0060 | 0.0037 | 0.0839 |
| 44 | 2026-09-29 | 2026-09-29T15:41:23 | +918897908470 | 72.68 | 2 | 0.0742 | 0.0060 | 0.0039 | 0.0841 |
| 45 | 2026-09-29 | 2026-09-29T16:06:09 | +918897908470 | 59.38 | 1 | 0.0371 | 0.0040 | 0.0032 | 0.0443 |
| 46 | 2026-09-29 | 2026-09-29T16:08:14 | +919398247132 | 97.12 | 2 | 0.0742 | 0.0080 | 0.0052 | 0.0874 |
| 47 | 2026-09-29 | 2026-09-29T17:44:40 | +919618474960 | 55.58 | 1 | 0.0371 | 0.0040 | 0.0030 | 0.0441 |
| 48 | 2026-09-29 | 2026-09-29T18:07:05 | +919398247132 | 83.16 | 2 | 0.0742 | 0.0060 | 0.0045 | 0.0847 |
| | **TOTAL** | | | **3256.8** | **79** | **2.9309** | **0.262** | **0.1747** | **3.3676** |

---

## 5. How Telnyx actually meters your calls

This is the part your internal model gets wrong. Three distinct behaviours, all verified against Telnyx's own `billed_sec` field:

### 5.1 Voice rounds UP to the next whole minute — per call

Telnyx bills `ceil(duration / 60s)` **per call**, not on a continuous stream.

- Verified exactly: my per-call `ceil()` model reproduces all 4 daily `billed_sec` figures for 25/27/28/29 Sep (17, 28, 11, 23 min = 4,740 s) **to the second**.
- Real talk time was **54.28 min**. Telnyx billed **79 min**.
- **You are billed 24.72 minutes you never talked = +45.5 % on voice.**

22 of 48 calls (45.8 %) are under 60 s and pay a full minute.

### 5.2 Recording is metered on the SUM of BOTH legs

Every one of your 48 calls produces **two** recording objects on the same `call_leg_id`:

| `initiated_by` | Rows | Typical duration |
|---|---:|---|
| `StartCallRecordingAPI` | 48 | ~3 s shorter |
| `Trunking` | 48 | full duration |
| **Total rows** | **96** | `channels: dual` on all |

Telnyx meters `ceil((legA + legB) / 60s)` per call:

- Modelled recording billed minutes: **131** vs Telnyx's **130** (99.2 % match; exact on 3 of 4 days).
- Recording billed **130 min** vs **54.28 min** of real talk = **2.4× over-metering**.

### 5.3 Media Streaming bills a different, shorter clock

| Meter | Billed seconds | Minutes |
|---|---:|---:|
| Voice (SIP / call-control) | 4,740 | 79.00 |
| Recording | 7,800 | 130.00 |
| **Media Streaming** | 2,960 | **49.33** |

Media Streaming bills **only 62 % of the voice window** — the stream is torn down at a different point in the call lifecycle than the media leg is billed. Rate is `$0.00354/min`.

### 5.4 Rate changes over the month — recording profile changed mid-month

| Period | Voice billed sec | Recording billed sec | Ratio |
|---|---:|---:|---:|
| 4–13 Sep (10 days) | 15,540 | 15,540 | **1.00×** |
| 14 Sep onward (9 days) | 10,500 | 15,300 | **1.46×** |

Recording and voice were metered **identically** for the first ten days of September, then diverged sharply from 14 Sep. That correlates with the per-call dual-leg pattern observed in the recordings. Worth confirming which recording configuration changed on/around 14 Sep — you may now be paying for a duplicate recording stream.

---

## 6. Findings

### F1 — CRITICAL — Account balance is $0.56

```
GET /v2/balance
{"balance":"0.56","available_credit":"0.56","credit_limit":"0.00","frozen":"0.00","pending":"0.00","currency":"USD"}
```

At the measured Sept rate of **~$0.065/connected call**, $0.56 buys roughly **8 connected calls** — or ~11 attempts in total, since failed dials are not charged. At the 25–29 Sep rate of 48 calls / 4 days ≈ 12 calls/day, that is **less than one day of traffic**.

Corroborating signal: **1 Oct shows 7 attempted, 0 connected, $0.00 charged.** A 100 % failure day right at the point where credit ran out is consistent with the carrier refusing to originate. There has been no traffic at all on 2–3 Oct.

**Action:** top up before any further testing, and add a balance-based kill-switch to the dial path so the app stops dialling into a dead account.

### F2 — CRITICAL — SIP trunking rate in `usage_pricing.py` is 74 % below actual

`server/services/usage_pricing.py:43-49`:

| Constant | App value | Telnyx actual | Delta |
|---|---:|---:|---|
| `TELNYX_VOICE_API_USD_PER_MIN` | $0.002 | $0.002 | ✅ exact |
| `TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN` | **$0.009** | **$0.0351** | ❌ **−74.4 %** |
| `TELNYX_MEDIA_STREAM_USD_PER_MIN` | $0.0035 | $0.00354 | ✅ −1.2 % |
| `TELNYX_CALL_RECORDING_USD_PER_MIN` | $0.002 | $0.002 | ⚠️ rate right, meter wrong (§5.2) |

There is **no `.env` override** for any of these (`.env` only sets `TELNYX_OUTBOUND_VOICE_PROFILE_ID`), so the hardcoded defaults are live.

`cost_telnyx_call_breakdown()` (`usage_pricing.py:700-746`) sums all four components per minute:

```
app model  = 0.002 + 0.009 + 0.0035 + 0.002 = $0.0165 / talk-minute
actual     = $0.0620 / talk-minute
understatement = 3.76×  (short by $0.0455 / talk-minute)
```

For the audited window the app would have booked **$0.90** against an **actual $3.37** — under-recording **$2.47 of real cost (73 %)**.

**Impact:** every internal margin, per-minute COGS figure, and any customer billing derived from `cost_telnyx_call_usd()` is wrong. If customer charges are anchored to this, you are **selling below cost by roughly 4× on telephony**.

**Action:** set `TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN=0.0351` in `.env` (the constant is already env-overridable via `_telnyx_env_float`), then correct the metering basis per §5.

### F3 — HIGH — Per-call minute rounding is not modelled (+45.5 % on voice)

`cost_telnyx_call_breakdown()` uses `duration_sec / 60` — continuous wall-clock. Telnyx bills `ceil()` per call.

- Real talk: **54.28 min** → app books 54.28 min
- Telnyx bills: **79 min** → **+24.72 min (+45.5 %) unrecorded**

**Action:** change the billing basis to `ceil(duration_sec / 60)` per call. Note the knock-on for customers: if you pass talk time through, short calls look cheaper than they are.

### F4 — HIGH — Recording metered on both legs (2.4× over-metering)

96 recording rows exist for 48 calls (one `StartCallRecordingAPI` + one `Trunking` per `call_leg_id`). Recording is billed on summed leg time — **130 billed minutes for 54.28 minutes of conversation**.

**Action:** determine whether the dual-leg/dual-channel recording is intended. If only one stream is retained and used, one of the two legs is pure waste. At `$0.002/min` the absolute loss is small ($0.26 this window), but it indicates a recording-configuration change around 14 Sep (§5.4) that should be understood.

### F5 — MEDIUM — 29.4 % of call attempts never connect

20 of 68 attempts failed, including **7 `recv_refuse`** (remote explicitly refused) and 4 `send_cancel`. Telnyx correctly charges $0 for these — no direct cost — but a 70.6 % connect rate caps effective throughput and skews per-call cost upward (you pay the fixed costs of the whole stack for a fraction of productive calls).

**Action:** correlate the 7 `recv_refuse` on 1 Oct with test-plan/disposition logic. If those are numbers that shouldn't be dialled, you are burning carrier-side reputation for no revenue.

### F6 — MEDIUM — No cost diversity, no traffic since 1 Oct

100 % of spend is one route: US DID `+13526146416` → Indian mobile (`country_iso: IN`), via one connection and one outbound profile. There is **no fallback route and no rate diversity** — a single carrier rate card and a single carrier relationship govern all cost. Combined with a $0.56 balance, there is no resilience at all.

### F7 — LOW — `call-control` Voice API cost is near-irrelevant (4.7 %)

`call-control` costs $0.002/min — **12 % of the SIP rate** — and contributes only 4.7 % of total spend. Any optimisation effort here has a 4.7 % ceiling. Focus entirely on SIP trunking.

### F8 — INFO — Billing window caps at 31 days

`/v2/usage_reports` rejects ranges > 31 days (`"start/end date difference less or equals to 31 days"`). Any recurring cost reporting must chunk windows. Also note the API requires `start_date`/`end_date` (not `start_time`/`end_time`), enumerates valid `product`/`dimensions`/`metrics` in its 400 responses, and `/v2/calls` returns 404 on this account — call-level data is only available via `/v2/recordings`, which returns **both** legs and therefore double-counts unless deduplicated by `call_leg_id`.

---

## 7. September full-month context

| Product | Billed min | Cost | Share |
|---|---:|---:|---:|
| `sip-trunking` | 434.00 | $15.2334 | 84.6 % |
| `recording` | 514.00 | $1.0280 | 5.7 % |
| `media-streaming` | 249.77 | $0.8858 | 4.9 % |
| `call-control` | 434.00 | $0.8680 | 4.8 % |
| **September total** | | **$18.0152** | |

- 364 attempted, 276 connected (**75.8 %** connect rate) across 19 active days
- 17,459 s talk = 290.98 min; billed 434 min (**+49 %**)
- **$0.0653 per connected call**, $0.0495 per attempt
- SIP rate held at exactly `$0.0351/min` on all 19 days — no rate drift
- Sep 4 alone: 63 calls, $3.47 (19.3 % of the month)

---

## 8. Recommended actions, in order

1. **Top up the Telnyx balance now** ($0.56 remaining; ~8 calls of runway). Add an automatic pre-dial balance check.
2. **Correct `TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN` to `0.0351`** in `.env`. This is a one-line change with a 3.76× effect on recorded telephony cost.
3. **Re-base cost on billed minutes**, not wall-clock: `ceil(duration_sec/60)` per call. Recompute historical margins before trusting any dashboard.
4. **Investigate the recording configuration change of 14 Sep** and whether both legs need to be recorded.
5. **Chase the 29.4 % connect failure rate**, starting with the 7 `recv_refuse` on 1 Oct.
6. **Add a cost dashboard** reading `usage_reports` per product, so drift in any rate is caught in days rather than at month-end. The four product/rate pairs in §2 are the baseline.

---

## Appendix — How this was produced

Live calls to Telnyx API v2 using the production key from `.env`. No estimated or published rate-card figures are used anywhere in this report — every rate is derived from Telnyx's own `cost` and `billed_sec` fields.

| Purpose | Endpoint |
|---|---|
| Balance | `GET /v2/balance` |
| Number / connection detail | `GET /v2/phone_numbers/3041007512695342943`, `GET /v2/connections` |
| Per-call durations | `GET /v2/recordings?filter[created_at][gte]=2026-09-25` (96 rows → 48 calls) |
| Billing by product/date | `GET /v2/usage_reports?product=…&dimensions=date&metrics=…&start_date=…&end_date=…` |
| Billing by outcome | `GET /v2/usage_reports?product=sip-trunking&dimensions=hangup_details` |
| Route attributes | `dimensions=direction\|country_iso\|source_country_code\|tn_type\|connection_type\|short_duration_call` |

All 39 billable products were enumerated and queried; only four carry spend (`sip-trunking`, `recording`, `media-streaming`, `call-control`). The remaining 35 — including `messaging`, `speech-to-text`, `ai-voice-assistant`, `conversation-relay`, `media-storage`, `number-lookup`, `webrtc` — returned zero usage, so this cost model is complete.

**Note on security:** the `TELNYX_API_KEY` used here is a live production credential committed in `.env`. It should be rotated and moved to secret storage.