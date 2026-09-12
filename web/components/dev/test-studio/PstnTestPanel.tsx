"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { ensureArray } from "@/lib/ensure-array";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import { LiveMediaFlowDebugger } from "./LiveMediaFlowDebugger";
import { CallAudioPanel } from "@/components/calls/detail/CallAudioPanel";
import type { StackForm, StackMode } from "@/lib/test-studio-stack";
import { effectivePstnLiveLlm, TEST_STUDIO_SESSION_ID } from "@/lib/test-studio-stack";
import { DEFAULT_CARTESIA_VOICE_ID, ensureTtsVoice } from "@/lib/voice/tts-config";
import { formatDuration, pipelineLabel } from "@/lib/call-list-utils";
import { formatInr } from "@/lib/usage-cost";

type ProviderStatus = {
  id: string;
  label?: string;
  enabled?: boolean;
  configured?: boolean;
  handshake_ok?: boolean;
  handshake_error?: string | null;
  ready?: boolean;
  ready_for_india?: boolean;
  upgrade_required_for_india?: boolean;
  phone_number?: string | null;
  connection_id?: string | null;
  webhook_url?: string | null;
  stream_ws?: string | null;
  answer_url?: string | null;
  passthru_url?: string | null;
  status_callback_url?: string | null;
  exophone?: string | null;
  balance?: string | null;
  checklist?: TelnyxChecklist;
};

type TelnyxChecklist = {
  call_control_app?: boolean;
  webhook_configured?: boolean;
  outbound_profile_on_app?: boolean;
  call_recording_on_profile?: boolean;
  international_india?: boolean;
  phone_number_active?: boolean;
  ready_for_us_ca?: boolean;
  ready_for_india?: boolean;
  upgrade_required_for_india?: boolean;
  verified_numbers?: string[];
  balance_usd?: number;
  whitelisted_destinations?: string[];
  errors?: string[];
};

type TelephonyStatus = {
  active_provider?: string;
  active_ready?: boolean;
  providers?: ProviderStatus[];
};

type CallRow = {
  call_sid?: string;
  call_control_id?: string;
  call_uuid?: string;
  status?: string;
  from?: string;
  to?: string;
  direction?: string;
  last_event?: string;
  internal_call_id?: string;
  updated_at?: number;
  media_frames_in?: number;
  media_frames_out?: number;
  bidirectional_ok?: boolean;
  pipeline?: string;
  duration_sec?: number;
  cost_inr?: number;
  cost_usd?: number;
  has_recording?: boolean;
  end_reason?: string;
};

const PROVIDERS = [
  { id: "exotel", label: "Exotel" },
  { id: "telnyx", label: "Telnyx" },
  { id: "plivo", label: "Plivo" },
] as const;

function providerLabel(id: string) {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

function callKey(c: CallRow) {
  return c.call_sid || c.call_control_id || c.call_uuid || String(c.updated_at || "");
}

function voiceLabel(provider: string, voiceId: string): string {
  const id = (voiceId || "").trim();
  if (!id) return provider === "cartesia" ? "Skylar (default)" : "shubh (default)";
  if (id === DEFAULT_CARTESIA_VOICE_ID) return "Skylar (default)";
  if (id.length > 20) return `${id.slice(0, 8)}…`;
  return id;
}

export function PstnTestPanel({
  agentId,
  sourceSessionId = TEST_STUDIO_SESSION_ID,
  tier,
  language,
  stackMode = "tier",
  stack,
  runtimeTtsSpeaker = "",
  runtimeOpenAiModel = "",
  stackOverride,
  onInternalCallStart,
  onInternalCallEnd,
  onReviewCall,
}: {
  agentId: string;
  sourceSessionId?: string;
  tier: string;
  language?: string;
  stackMode?: StackMode;
  stack?: StackForm;
  runtimeTtsSpeaker?: string;
  runtimeOpenAiModel?: string;
  stackOverride?: Record<string, unknown>;
  onInternalCallStart?: (callId: string) => void;
  onInternalCallEnd?: (callId: string) => void;
  onReviewCall?: (callId: string) => void;
}) {
  const [status, setStatus] = useState<TelephonyStatus | null>(null);
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [stackPreview, setStackPreview] = useState<string>("");
  const [fromE164, setFromE164] = useState("");
  const [toE164, setToE164] = useState("");
  const [providerDraft, setProviderDraft] = useState("telnyx");
  const [verifyCode, setVerifyCode] = useState("");
  const [trackedCallId, setTrackedCallId] = useState<string | null>(null);
  const [listenCallId, setListenCallId] = useState<string | null>(null);
  const trackedCallRef = useRef<string | null>(null);
  const endedOnceRef = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dialingRef = useRef(false);
  const fromInitRef = useRef(false);

  const active = status?.active_provider || providerDraft;
  const activeSt = status?.providers?.find((p) => p.id === active);

  const enabledProviders = useMemo(() => {
    if (!status?.providers?.length) return [];
    return PROVIDERS.filter((p) => status.providers?.find((s) => s.id === p.id)?.enabled);
  }, [status]);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      await refreshPortalSession("dev");
      const [stR, callsR] = await Promise.all([
        portalFetch("dev", "/api/dev/telephony/status"),
        portalFetch("dev", "/api/dev/telephony/calls"),
      ]);
      if (!stR.ok) {
        const errBody = await stR.text().catch(() => "");
        setLoadError(
          stR.status === 401
            ? "Dev session required — sign in at /dev/login"
            : `Telephony status failed (${stR.status})${errBody ? `: ${errBody.slice(0, 120)}` : ""}`
        );
        return;
      }
      const j = await stR.json();
      setStatus(j);
      if (j.active_provider) setProviderDraft(j.active_provider);
      const phone = j.providers?.find((p: ProviderStatus) => p.id === j.active_provider)?.phone_number;
      if (phone && !fromInitRef.current) {
        fromInitRef.current = true;
        setFromE164(phone);
      }
      if (callsR.ok) {
        const callsJ = await callsR.json();
        setCalls(ensureArray<CallRow>(callsJ.calls));
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load telephony status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const r = await portalFetch("dev", "/api/dev/telephony/calls");
      if (!r.ok) return;
      const j = await r.json();
      const rows = ensureArray<CallRow>(j.calls);
      setCalls(rows);
      for (const c of rows) {
        const internal = c.internal_call_id;
        if (!internal) continue;
        if (!trackedCallRef.current && onInternalCallStart) {
          trackedCallRef.current = internal;
          setTrackedCallId(internal);
          endedOnceRef.current = null;
          onInternalCallStart(internal);
        }
        const st = (c.status || "").toLowerCase();
        if (
          trackedCallRef.current === internal &&
          st &&
          ["completed", "failed", "busy", "no-answer", "canceled", "hangup"].includes(st) &&
          onInternalCallEnd &&
          endedOnceRef.current !== internal
        ) {
          endedOnceRef.current = internal;
          onInternalCallEnd(internal);
          setListenCallId(internal);
          trackedCallRef.current = null;
        }
      }
    }, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [onInternalCallStart, onInternalCallEnd]);

  async function setProvider(next: string) {
    setProviderDraft(next);
    setBusy(true);
    setMessage(`Switching provider to ${providerLabel(next)}…`);
    const r = await portalFetch("dev", "/api/dev/telephony/provider", {
      method: "PATCH",
      body: JSON.stringify({ provider: next }),
    });
    setMessage(r.ok ? `Active provider: ${providerLabel(next)}` : "Failed to switch provider");
    setBusy(false);
    await load();
  }

  async function runHandshake() {
    setBusy(true);
    setMessage(`Running ${providerLabel(active)} handshake…`);
    const r = await portalFetch("dev", "/api/dev/telephony/handshake", { method: "POST" });
    const j = await r.json();
    if (r.ok && (j.ok || j.handshake?.ok)) {
      const balance = j.balance ?? j.handshake?.balance;
      setMessage(`Handshake OK${balance ? ` · balance ${balance}` : ""}`);
    } else {
      setMessage(`Handshake failed: ${j.error?.message || j.error || j.handshake_error || "unknown"}`);
    }
    setBusy(false);
    await load();
  }

  const liveLlm = useMemo(
    () => effectivePstnLiveLlm(runtimeOpenAiModel, stack?.llmModel),
    [runtimeOpenAiModel, stack?.llmModel]
  );
  const realtimeE2e = stackOverride?.pipeline === "realtime_voice";
  const realtimeVoice = useMemo(() => {
    const block = stackOverride?.realtime_voice;
    if (!block || typeof block !== "object") return null;
    return block as Record<string, unknown>;
  }, [stackOverride]);
  const stackOverrideKey = useMemo(
    () => (stackOverride ? JSON.stringify(stackOverride) : ""),
    [stackOverride]
  );
  const lastValidatedKeyRef = useRef("");
  const validateInFlightRef = useRef(false);

  useEffect(() => {
    if (!stackOverrideKey) {
      setStackPreview(stackMode === "tier" ? "Using Test Studio tier + fine-tune from session" : "");
      return;
    }
    const validateKey = `${stackMode}|${stackOverrideKey}|${tier}|${language}`;
    if (lastValidatedKeyRef.current === validateKey) return;

    let cancelled = false;
    const timer = setTimeout(() => {
      (async () => {
        if (validateInFlightRef.current) return;
        validateInFlightRef.current = true;
        try {
          await refreshPortalSession("dev");
          const parsed = JSON.parse(stackOverrideKey) as Record<string, unknown>;
          const r = await portalFetch("dev", "/api/dev/telephony/pstn-stack/validate", {
            method: "POST",
            body: JSON.stringify({
              tier: tier || "medium",
              language: language || "te-IN",
              stackOverride: parsed,
            }),
          });
          if (cancelled) return;
          if (r.status === 429) {
            setStackPreview("Rate limited — stack checks paused briefly");
            return;
          }
          const raw = await r.text();
          let j: { ok?: boolean; adjustments?: string[]; validation_errors?: string[]; error?: string } = {};
          try {
            j = raw ? JSON.parse(raw) : {};
          } catch {
            if (!cancelled) setStackPreview("Stack check unavailable (API reconnecting)");
            return;
          }
          if (j.ok) {
            lastValidatedKeyRef.current = validateKey;
            const adj = Array.isArray(j.adjustments) && j.adjustments.length
              ? ` · auto-fix: ${j.adjustments.join("; ")}`
              : "";
            setStackPreview(`Stack OK for PSTN${adj}`);
          } else {
            const errs = j.validation_errors?.length ? j.validation_errors.join("; ") : j.error;
            setStackPreview(`Stack error: ${errs || "invalid"}`);
          }
        } catch {
          if (!cancelled) setStackPreview("Stack check unavailable (API reconnecting)");
        } finally {
          validateInFlightRef.current = false;
        }
      })();
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [stackMode, stackOverrideKey, tier, language]);

  async function outboundDial() {
    if (!toE164.trim()) {
      setMessage("Enter destination number");
      return;
    }
    if (dialingRef.current || busy) {
      return;
    }
    dialingRef.current = true;
    setBusy(true);
    trackedCallRef.current = null;
    setTrackedCallId(null);
    setMessage(`Placing ${providerLabel(active)} outbound call…`);
    try {
      const dialBody: Record<string, unknown> = {
        toE164: toE164.trim(),
        fromE164: fromE164.trim() || undefined,
        agentId,
        tier: tier || "medium",
        language: language || "te-IN",
        inheritTestStudioConfig: true,
        sourceSessionId,
      };
      if (stackOverride) {
        dialBody.stackOverride = stackOverride;
      }
      const r = await portalFetch("dev", "/api/dev/telephony/outbound", {
        method: "POST",
        body: JSON.stringify(dialBody),
      });
      const j = await r.json();
      const apiOk = r.ok && (j.ok === undefined || j.ok === true);
      const adj =
        Array.isArray(j.stack_adjustments) && j.stack_adjustments.length
          ? ` · ${j.stack_adjustments.join("; ")}`
          : "";
      const errDetail =
        j.validation_errors?.length ? j.validation_errors.join("; ") : j.error?.message || j.error || j.body;
      setMessage(
        apiOk
          ? `Call initiated · ${j.call_sid || j.call_control_id || j.call_uuid || "queued"}${adj}`
          : errDetail || "Outbound failed"
      );
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Outbound failed");
    } finally {
      dialingRef.current = false;
      setBusy(false);
    }
  }

  async function runTelnyxSetup() {
    setBusy(true);
    setMessage("Applying standard Telnyx settings (webhook, OVP, recording)…");
    const r = await portalFetch("dev", "/api/dev/telephony/telnyx/setup", { method: "POST" });
    const j = await r.json();
    setMessage(r.ok ? "Telnyx standard setup applied" : j.error || "Setup failed");
    setBusy(false);
    await load();
  }

  async function requestVerifyNumber() {
    setBusy(true);
    setMessage(`Sending verification to ${toE164}…`);
    const r = await portalFetch("dev", "/api/dev/telephony/telnyx/verify-number", {
      method: "POST",
      body: JSON.stringify({ phoneNumber: toE164.trim(), method: "sms" }),
    });
    const j = await r.json();
    setMessage(r.ok ? "Verification SMS sent — enter code below" : j.error || j.body || "Verify failed");
    setBusy(false);
  }

  async function confirmVerifyNumber() {
    if (!verifyCode.trim()) return;
    setBusy(true);
    const r = await portalFetch("dev", "/api/dev/telephony/telnyx/verify-number/confirm", {
      method: "POST",
      body: JSON.stringify({ phoneNumber: toE164.trim(), code: verifyCode.trim() }),
    });
    const j = await r.json();
    setMessage(r.ok ? "Number verified — retry outbound call" : j.error || j.body || "Confirm failed");
    setBusy(false);
    if (r.ok) await load();
  }

  async function searchTelnyxNumbers() {
    setBusy(true);
    setMessage("Searching Telnyx IN numbers…");
    const r = await portalFetch("dev", "/api/dev/telephony/telnyx/numbers/search", { method: "POST" });
    const j = await r.json();
    if (r.ok && j.numbers?.length) {
      const first = j.numbers[0]?.phone_number || j.numbers[0]?.e164;
      setMessage(`Found ${j.numbers.length} numbers · first ${first || "—"}`);
    } else {
      setMessage("No numbers found or search failed");
    }
    setBusy(false);
  }

  if (loading) {
    return (
      <p className="text-sm text-text-muted">
        Loading telephony status…
        <span className="mt-1 block text-xs text-text-subtle">
          Checking Exotel, Telnyx, and Plivo handshakes (usually under 10s).
        </span>
      </p>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm">
        <p className="font-medium text-danger">{loadError}</p>
        <Button type="button" variant="secondary" className="mt-3" onClick={() => { setLoading(true); load(); }}>
          Retry status check
        </Button>
      </div>
    );
  }

  const notReady = !activeSt?.ready;

  const telnyxChecklist = active === "telnyx" ? activeSt?.checklist : undefined;
  const indiaBlocked = Boolean(activeSt?.upgrade_required_for_india && !telnyxChecklist?.international_india);
  const destVerified = telnyxChecklist?.verified_numbers?.includes(toE164.trim());
  const telnyxReady = Boolean(status?.providers?.find((p) => p.id === "telnyx")?.ready);
  const useValidatedPath = active === "telnyx";
  const ttsVoice = stack
    ? ensureTtsVoice(stack.ttsProvider, stack.ttsVoiceId || runtimeTtsSpeaker, stack.ttsModel)
    : runtimeTtsSpeaker;
  const ttsProvider = stack?.ttsProvider || "—";
  const ttsModel = stack?.ttsModel || "—";

  return (
    <div className="space-y-6">
      {telnyxReady && !useValidatedPath && (
        <p className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm text-text-muted">
          Validation tests 1–10 use <strong className="text-text">Telnyx L16 @ 16 kHz</strong>. Switch to Telnyx
          for the same audio architecture as automated tests.
        </p>
      )}
      <DevCard title="SIP trunk provider" description="Only enabled providers from Environment are shown">
        {enabledProviders.length === 0 ? (
          <p className="rounded-xl border border-dashed border-warning/40 bg-warning/5 px-4 py-3 text-sm text-warning">
            No PSTN providers enabled. Turn on Exotel, Telnyx, or Plivo in{" "}
            <Link href="/dev/environment" className="text-accent hover:underline">Environment</Link> and save keys.
          </p>
        ) : (
        <div className="flex flex-wrap gap-2">
          {enabledProviders.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setProvider(p.id)}
              className={`rounded-xl border px-4 py-2 text-sm font-medium transition-colors ${
                active === p.id
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-surface-border text-text-muted hover:bg-surface-raised"
              }`}
            >
              {p.label}
              {status?.active_provider === p.id && (
                <span className="ml-2 text-xs text-success">(active)</span>
              )}
              {status?.providers?.find((s) => s.id === p.id)?.ready === false && (
                <span className="ml-2 text-xs text-warning">(not ready)</span>
              )}
            </button>
          ))}
        </div>
        )}
        {activeSt && !activeSt.enabled && (
          <p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
            Active provider {providerLabel(active)} is disabled in Environment. Enable it or switch provider.
          </p>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Configure keys in{" "}
          <Link href="/dev/environment" className="text-accent hover:underline">Environment</Link>
          . Public tunnel required for media WebSocket (
          <span className="font-mono">{activeSt?.stream_ws || activeSt?.status_callback_url || "—"}</span>).
        </p>
      </DevCard>

      {active === "telnyx" && telnyxChecklist && (
        <DevCard title="Telnyx Mission Control checklist" description="Standard settings applied to every new number">
          <ul className="space-y-1 text-sm text-text-muted">
            <li>{telnyxChecklist.call_control_app ? "✓" : "○"} Call Control app active</li>
            <li>{telnyxChecklist.webhook_configured ? "✓" : "○"} Webhook URL configured</li>
            <li>{telnyxChecklist.outbound_profile_on_app ? "✓" : "○"} Outbound voice profile linked</li>
            <li>{telnyxChecklist.call_recording_on_profile ? "✓" : "○"} Call recording on profile (dual WAV)</li>
            <li>{telnyxChecklist.phone_number_active ? "✓" : "○"} From number active</li>
            <li>{telnyxChecklist.international_india ? "✓" : "○"} India in whitelist</li>
          </ul>
          {indiaBlocked && (
            <p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              India outbound requires Telnyx account upgrade (Level 2+) or verify destination number on trial.
              <a href="https://telnyx.com/upgrade" className="ml-1 text-accent hover:underline" target="_blank" rel="noreferrer">
                Upgrade account
              </a>
            </p>
          )}
          {telnyxChecklist.verified_numbers?.length ? (
            <p className="mt-2 text-xs text-text-muted">
              Verified: {telnyxChecklist.verified_numbers.join(", ")}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={runTelnyxSetup} disabled={busy}>
              Apply standard setup
            </Button>
          </div>
        </DevCard>
      )}

      {notReady ? (
        <DevCard title={`PSTN · ${providerLabel(active)}`} description="Provider not ready">
          <div className="rounded-xl border border-dashed border-warning/40 bg-warning/5 p-5">
            <p className="font-medium text-warning">{providerLabel(active)} not ready</p>
            {activeSt?.handshake_error && (
              <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{activeSt.handshake_error}</p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" onClick={runHandshake} disabled={busy}>
                Test handshake
              </Button>
              <Link href="/dev/environment" className="inline-flex items-center text-sm font-medium text-accent hover:underline">
                Open Environment →
              </Link>
            </div>
          </div>
        </DevCard>
      ) : (
        <DevCard title={`${providerLabel(active)} handshake`} description="Credentials verified">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-text-muted">Phone number</dt>
              <dd className="mt-1 font-mono text-text">{activeSt?.phone_number || activeSt?.exophone || "—"}</dd>
            </div>
            {activeSt?.balance && (
              <div>
                <dt className="text-text-muted">Balance</dt>
                <dd className="mt-1 font-mono text-text">{activeSt.balance}</dd>
              </div>
            )}
            {activeSt?.connection_id && (
              <div>
                <dt className="text-text-muted">Connection ID</dt>
                <dd className="mt-1 font-mono text-xs">{activeSt.connection_id}</dd>
              </div>
            )}
            {activeSt?.stream_ws && (
              <div className="sm:col-span-2">
                <dt className="text-text-muted">Media WebSocket</dt>
                <dd className="mt-1 font-mono text-xs break-all">{activeSt.stream_ws}</dd>
              </div>
            )}
          </dl>
          <Button type="button" variant="secondary" className="mt-4" onClick={runHandshake} disabled={busy}>
            Re-test handshake
          </Button>
        </DevCard>
      )}

        <DevCard
        title="Agent voice & stack"
        description={
          realtimeE2e
            ? "Telnyx PCM ↔ OpenAI Realtime audio — same compiled brain as Agent only"
            : "Same Test Studio script, stack, voice, and fine-tune as Agent only (browser)"
        }
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-text-muted">Stack</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {realtimeE2e ? "realtime audio E2E" : stackMode === "custom" ? "custom" : `tier · ${tier || "medium"}`}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">Language</dt>
            <dd className="mt-1 font-mono text-xs text-text">{language || "te-IN"}</dd>
          </div>
          {realtimeE2e ? (
            <>
          <div>
            <dt className="text-text-muted">Realtime model</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {liveLlm.provider} / {liveLlm.model}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">OpenAI voice</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {String(realtimeVoice?.voice || stack?.realtimeVoice || "marin")}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">Turn detection</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {String(realtimeVoice?.turn_detection || stack?.realtimeTurnDetection || "semantic_vad")}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">VAD / noise</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {String(realtimeVoice?.vad_eagerness || stack?.realtimeVadEagerness || "medium")}
              {" · "}
              {String(realtimeVoice?.noise_reduction || stack?.realtimeNoiseReduction || "far_field")}
            </dd>
          </div>
            </>
          ) : (
            <>
          <div>
            <dt className="text-text-muted">STT</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {stack ? `${stack.sttProvider} / ${stack.sttModel}` : "tier default"}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">LLM (live)</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {liveLlm.provider} / {liveLlm.model}
            </dd>
          </div>
          {stackMode === "custom" && stack?.llmProvider && stack.llmProvider !== liveLlm.provider ? (
            <div className="sm:col-span-2">
              <p className="text-[11px] text-text-subtle">
                Custom stack lists {stack.llmProvider}/{stack.llmModel}; PSTN live turns always use OpenAI
                Realtime. Script compile and post-call use the HTTP model from fine-tune.
              </p>
            </div>
          ) : null}
          <div>
            <dt className="text-text-muted">TTS</dt>
            <dd className="mt-1 font-mono text-xs text-text">
              {ttsProvider} / {ttsModel}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">Agent voice</dt>
            <dd className="mt-1 font-mono text-xs text-text">{voiceLabel(ttsProvider, ttsVoice)}</dd>
          </div>
            </>
          )}
        </dl>
        <p
          className={`mt-3 text-[11px] ${
            stackPreview.startsWith("Stack error") ? "text-danger" : "text-text-subtle"
          }`}
        >
          Script + VAD + LLM fine-tune from session{" "}
          <span className="font-mono">{sourceSessionId}</span>
          {stackPreview ? ` · ${stackPreview}` : ""}
        </p>
      </DevCard>

      <DevCard title="Outbound test call" description="Full E2E — PSTN dials customer, agent stack streams audio">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-text-muted">From (caller ID)</span>
            <input
              type="text"
              value={fromE164}
              onChange={(e) => setFromE164(e.target.value)}
              placeholder="+91XXXXXXXXXX"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">To (customer)</span>
            <input
              type="text"
              value={toE164}
              onChange={(e) => setToE164(e.target.value)}
              placeholder="+91XXXXXXXXXX"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" onClick={outboundDial} disabled={busy || notReady}>
            {busy ? "Dialing…" : "Place outbound call"}
          </Button>
          {active === "telnyx" && (
            <>
              <Button type="button" variant="secondary" onClick={searchTelnyxNumbers} disabled={busy}>
                Search IN numbers
              </Button>
              {indiaBlocked && !destVerified && (
                <Button type="button" variant="secondary" onClick={requestVerifyNumber} disabled={busy}>
                  Verify destination (SMS)
                </Button>
              )}
            </>
          )}
        </div>
        {active === "telnyx" && indiaBlocked && !destVerified && (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="block text-sm">
              <span className="text-text-muted">SMS verification code</span>
              <input
                type="text"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value)}
                placeholder="6-digit code"
                className="mt-2 w-40 rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
              />
            </label>
            <Button type="button" variant="secondary" onClick={confirmVerifyNumber} disabled={busy}>
              Confirm verify
            </Button>
          </div>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Place outbound uses this stack, voice, and Test Studio fine-tune — same as the browser agent.
        </p>
      </DevCard>

      {active === "telnyx" ? (
        <LiveMediaFlowDebugger callId={trackedCallId} />
      ) : null}

      {listenCallId ? (
        <CallAudioPanel
          callId={listenCallId}
          title="Listen to recording"
          description="Mix, caller, and agent WAV — play after hangup"
        />
      ) : null}

      <DevCard title="Recent PSTN calls" description="After hangup: Play recording here, or Review for transcript and cost">
        <div className="overflow-x-auto rounded-xl border border-surface-border-subtle">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-surface-border-subtle bg-surface-raised text-xs text-text-muted">
              <tr>
                <th className="px-3 py-2">Provider ID</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Stream</th>
                <th className="px-3 py-2">Pipeline</th>
                <th className="px-3 py-2">Duration</th>
                <th className="px-3 py-2">Cost</th>
                <th className="px-3 py-2">Internal call</th>
                <th className="px-3 py-2">Route</th>
              </tr>
            </thead>
            <tbody>
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-4 text-text-muted">No calls yet.</td>
                </tr>
              ) : (
                calls.map((c) => (
                  <tr key={callKey(c)} className="border-b border-surface-border-subtle/50">
                    <td className="px-3 py-2 font-mono text-xs">{callKey(c).slice(0, 24)}…</td>
                    <td className="px-3 py-2">{c.status || "—"}</td>
                    <td className="px-3 py-2 text-xs">
                      {c.bidirectional_ok
                        ? `✓ in ${c.media_frames_in ?? 0} / out ${c.media_frames_out ?? 0}`
                        : c.internal_call_id
                          ? `in ${c.media_frames_in ?? 0} / out ${c.media_frames_out ?? 0}`
                          : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">{pipelineLabel(c.pipeline, "pstn")}</td>
                    <td className="px-3 py-2 font-mono text-xs">{formatDuration(c.duration_sec)}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {c.cost_inr != null ? formatInr(Number(c.cost_inr)) : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {c.internal_call_id ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className="text-accent-primary underline-offset-2 hover:underline"
                            onClick={() => {
                              setListenCallId(c.internal_call_id!);
                              onReviewCall?.(c.internal_call_id!);
                            }}
                          >
                            Review
                          </button>
                          <button
                            type="button"
                            className="text-[10px] uppercase tracking-wide text-accent-primary hover:underline"
                            onClick={() => setListenCallId(c.internal_call_id!)}
                          >
                            Play
                          </button>
                          {c.has_recording ? (
                            <Link
                              href={`/app/calls/${c.internal_call_id}`}
                              className="text-[10px] uppercase tracking-wide text-text-subtle hover:text-text"
                            >
                              Archive
                            </Link>
                          ) : null}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{c.from || "—"} → {c.to || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </DevCard>

      {message && <p className="text-sm text-text-muted">{message}</p>}
    </div>
  );
}
