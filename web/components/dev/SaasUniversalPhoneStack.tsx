"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { useStackCatalog } from "@/components/test-studio/useStackCatalog";
import { portalFetch } from "@/lib/auth-client";
import {
  DEFAULT_REALTIME_VOICE,
  REALTIME_NOISE_REDUCTION,
  REALTIME_TURN_DETECTION,
  REALTIME_VAD_EAGERNESS,
  REALTIME_VOICE_OPTIONS,
  realtimeVoiceOptionLabel,
  isGeminiLiveVoiceModel,
  isRealtimeSpeechToSpeechModel,
  normalizeRealtimeSpeed,
} from "@/lib/realtime-voice";
import {
  geminiMappedVoice,
  saasPhoneStackFromOverride,
  saasPhoneStackToOverride,
  SAAS_PHONE_LANGUAGES,
} from "@/lib/saas-phone-stack-form";
import {
  buildPstnRealtimeStackOverride,
  realtimeSpeechModelOptions,
  type StackForm,
} from "@/lib/test-studio-stack";

type Credentials = {
  openai?: { configured?: boolean };
  gemini?: { enabled?: boolean; configured?: boolean; ready?: boolean };
};

type TelephonyProviderStatus = {
  id: string;
  label?: string;
  enabled?: boolean;
  configured?: boolean;
  ready?: boolean;
  handshake_ok?: boolean;
  handshake_error?: string | null;
  phone_number?: string | null;
  balance?: string | number | null;
  connection_id?: string | null;
  webhook_url?: string | null;
  answer_url?: string | null;
  fallback_url?: string | null;
  hangup_url?: string | null;
  recording_url?: string | null;
  stream_ws?: string | null;
  account_info?: {
    auth_id?: string;
    app_id?: string;
    account_name?: string | null;
  };
  checklist?: {
    balance_usd?: number;
    whitelisted_destinations?: string[];
    ready_for_us_ca?: boolean;
    ready_for_india?: boolean;
  };
};

type TelephonySummary = {
  active_provider?: string;
  active_enabled?: boolean;
  active_ready?: boolean;
  providers?: TelephonyProviderStatus[];
  enabled_providers?: string[];
};

type Alignment = {
  ok?: boolean;
  liveProvider?: string;
  liveModel?: string;
  realtimeVoice?: string;
  language?: string;
  notes?: string[];
};

function defaultForm(): StackForm {
  const f = saasPhoneStackFromOverride({
    pipeline: "realtime_voice",
    language: "te-IN",
    llm: { provider: "openai", model: "gpt-realtime-2.1-mini" },
    realtime_voice: {
      voice: DEFAULT_REALTIME_VOICE,
      turn_detection: "semantic_vad",
      vad_eagerness: "high",
      noise_reduction: "far_field",
      speed: 1,
      silence_ms: 250,
    },
  });
  return f;
}

export function SaasUniversalPhoneStack() {
  const { providers, loading: catalogLoading, error: catalogError } = useStackCatalog("dev");
  const [form, setForm] = useState<StackForm>(defaultForm);
  const [resolved, setResolved] = useState<Record<string, unknown> | null>(null);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [telephony, setTelephony] = useState<TelephonySummary | null>(null);
  const [telephonyBusy, setTelephonyBusy] = useState(false);
  const [telephonyMsg, setTelephonyMsg] = useState("");
  const [alignment, setAlignment] = useState<Alignment | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [adjustments, setAdjustments] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [showJson, setShowJson] = useState(false);
  const [jsonEditor, setJsonEditor] = useState("");

  const speechModels = useMemo(() => realtimeSpeechModelOptions(providers), [providers]);
  const isGemini = isGeminiLiveVoiceModel(form.llmModel);
  const previewOverride = useMemo(() => saasPhoneStackToOverride(form), [form]);

  const patch = (patch: Partial<StackForm>) => setForm((prev) => ({ ...prev, ...patch }));

  const selectProvider = (provider: "openai" | "gemini") => {
    const row = speechModels.find((m) => m.provider === provider);
    if (row) {
      patch({ llmProvider: provider, llmModel: row.id });
      return;
    }
    patch({
      llmProvider: provider,
      llmModel: provider === "gemini" ? "gemini-3.8-live" : "gpt-realtime-2.1-mini",
    });
  };

  const load = useCallback(async () => {
    setLoading(true);
    const [stackR, telR] = await Promise.all([
      portalFetch("dev", "/api/dev/stack/saas-phone"),
      portalFetch("dev", "/api/dev/telephony/status").catch(() => null),
    ]);
    if (!stackR.ok) {
      setStatus(`Could not load SaaS phone stack (${stackR.status})`);
      setLoading(false);
      return;
    }
    const j = await stackR.json();
    const override = (j.saved?.stack_override || j.resolved) as Record<string, unknown> | undefined;
    if (override) {
      setForm(saasPhoneStackFromOverride(override));
    }
    if (j.resolved) setResolved(j.resolved as Record<string, unknown>);
    setCredentials(j.credentials as Credentials);
    setAlignment(j.alignment as Alignment);
    setWarnings(Array.isArray(j.warnings) ? j.warnings : []);
    setAdjustments(Array.isArray(j.adjustments) ? j.adjustments : []);
    setJsonEditor(JSON.stringify(override || j.resolved || {}, null, 2));

    if (telR && telR.ok) {
      const telJ = await telR.json().catch(() => null);
      if (telJ) setTelephony(telJ);
    }

    setStatus("");
    setLoading(false);
  }, []);

  const switchTelephony = async (providerId: string) => {
    if (telephonyBusy || telephony?.active_provider === providerId) return;
    setTelephonyBusy(true);
    setTelephonyMsg("");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/provider", {
        method: "PATCH",
        body: JSON.stringify({ provider: providerId }),
      });
      if (!r.ok) {
        setTelephonyMsg(`Failed to switch provider (${r.status})`);
        return;
      }
      const updatedR = await portalFetch("dev", "/api/dev/telephony/status");
      if (updatedR.ok) {
        const updatedJ = await updatedR.json();
        setTelephony(updatedJ);
        setTelephonyMsg(`Active telephony trunk switched to ${providerId.toUpperCase()}`);
      }
    } catch (e) {
      setTelephonyMsg(e instanceof Error ? e.message : "Failed to switch provider");
    } finally {
      setTelephonyBusy(false);
    }
  };

  const testHandshake = async () => {
    setTelephonyBusy(true);
    setTelephonyMsg("Testing carrier handshake…");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/handshake", { method: "POST" });
      const j = await r.json();
      if (j.ok) {
        setTelephonyMsg(`✓ Handshake OK (${telephony?.active_provider?.toUpperCase()}): Connected to API`);
      } else {
        setTelephonyMsg(`⚠ Handshake warning: ${j.error || JSON.stringify(j)}`);
      }
    } catch (e) {
      setTelephonyMsg(e instanceof Error ? e.message : "Handshake failed");
    } finally {
      setTelephonyBusy(false);
    }
  };

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setJsonEditor(JSON.stringify(previewOverride, null, 2));
  }, [previewOverride]);

  async function save() {
    setStatus("Saving…");
    let stackOverride: Record<string, unknown>;
    if (showJson) {
      try {
        stackOverride = JSON.parse(jsonEditor);
      } catch {
        setStatus("Invalid JSON in advanced editor");
        return;
      }
    } else {
      stackOverride = saasPhoneStackToOverride(form);
    }
    const r = await portalFetch("dev", "/api/dev/stack/saas-phone", {
      method: "PUT",
      body: JSON.stringify({ stackOverride, language: form.language }),
    });
    if (!r.ok) {
      setStatus(`Save failed (${r.status})`);
      return;
    }
    const j = await r.json();
    if (j.resolved) {
      setResolved(j.resolved as Record<string, unknown>);
      setForm(saasPhoneStackFromOverride(j.resolved as Record<string, unknown>));
    }
    setCredentials(j.credentials as Credentials);
    setAlignment(j.alignment as Alignment);
    setWarnings(Array.isArray(j.warnings) ? j.warnings : []);
    setAdjustments(Array.isArray(j.adjustments) ? j.adjustments : []);
    setStatus("Saved — applies to all subscriber PSTN and web practice calls.");
  }

  if (loading) {
    return <p className="text-sm text-text-muted">Loading SaaS phone stack…</p>;
  }

  const openaiReady = credentials?.openai?.configured;
  const geminiReady = credentials?.gemini?.ready;

  return (
    <div className="space-y-4">
      {/* Telephony Infrastructure & Carrier Selection */}
      <DevCard delayMs={0}>
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-text">Telephony Infrastructure & PSTN Calling Trunk</h2>
              <p className="text-sm text-text-muted mt-1">
                Configure whether Telnyx or Vobiz powers inbound and outbound carrier calling, number searching,
                and bidirectional WebSocket audio streaming.
              </p>
            </div>
            {telephony?.active_provider && (
              <span className="self-start sm:self-auto font-mono text-xs px-2.5 py-1 rounded-full bg-accent/10 text-accent font-semibold border border-accent/20">
                Active Trunk: {telephony.active_provider.toUpperCase()}
              </span>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {/* Telnyx Trunk Card */}
            {(() => {
              const telnyxSt = telephony?.providers?.find((p) => p.id === "telnyx");
              const isTelnyxActive = (telephony?.active_provider || "telnyx") === "telnyx";
              const isReady = Boolean(telnyxSt?.ready);
              return (
                <div
                  className={`rounded-xl border p-4 text-left transition-all ${
                    isTelnyxActive
                      ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                      : "border-border bg-surface hover:border-accent/40"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-text">Telnyx PSTN</p>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                        isReady ? "bg-status-success/10 text-status-success" : "bg-status-warning/10 text-status-warning"
                      }`}
                    >
                      {isReady ? "✓ Ready" : "⚠ Incomplete"}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted mt-1">
                    Call Control v2 · 8 kHz µ-law · Media streaming
                  </p>
                  <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                    <div>Caller ID: {telnyxSt?.phone_number || "Auto"}</div>
                    <div>Connection ID: {telnyxSt?.connection_id || "Configured"}</div>
                    <div>Webhook: /api/telnyx/webhook</div>
                    <div>Stream: /ws/telnyx-stream</div>
                  </div>
                  <div className="mt-3">
                    <Button
                      type="button"
                      variant={isTelnyxActive ? "primary" : "secondary"}
                      disabled={isTelnyxActive || telephonyBusy}
                      onClick={() => switchTelephony("telnyx")}
                      className="w-full text-xs"
                    >
                      {isTelnyxActive ? "Active Trunk" : "Switch to Telnyx"}
                    </Button>
                  </div>
                </div>
              );
            })()}

            {/* Vobiz Trunk Card */}
            {(() => {
              const vobizSt = telephony?.providers?.find((p) => p.id === "vobiz");
              const isVobizActive = telephony?.active_provider === "vobiz";
              const isReady = Boolean(vobizSt?.ready);
              return (
                <div
                  className={`rounded-xl border p-4 text-left transition-all ${
                    isVobizActive
                      ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                      : "border-border bg-surface hover:border-accent/40"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-text">Vobiz Telephony</p>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                        isReady ? "bg-status-success/10 text-status-success" : "bg-status-warning/10 text-status-warning"
                      }`}
                    >
                      {isReady ? "✓ Ready" : "⚠ Incomplete"}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted mt-1">
                    Voice XML + Bidirectional L16/µ-law WebSocket stream
                  </p>
                  <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                    <div>Auth ID: {vobizSt?.account_info?.auth_id || "MA_LX2CKOU1"}</div>
                    <div>App ID: {vobizSt?.account_info?.app_id || "551682"}</div>
                    <div>Answer URL: /api/vobiz/answer</div>
                    <div>Stream: /ws/vobiz-stream</div>
                  </div>
                  <div className="mt-3">
                    <Button
                      type="button"
                      variant={isVobizActive ? "primary" : "secondary"}
                      disabled={isVobizActive || telephonyBusy}
                      onClick={() => switchTelephony("vobiz")}
                      className="w-full text-xs"
                    >
                      {isVobizActive ? "Active Trunk" : "Switch to Vobiz"}
                    </Button>
                  </div>
                </div>
              );
            })()}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={telephonyBusy}
                onClick={testHandshake}
                className="text-xs"
              >
                Test Live Handshake
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={telephonyBusy}
                onClick={load}
                className="text-xs"
              >
                Refresh Telephony
              </Button>
            </div>
            {telephonyMsg && (
              <p className="text-xs font-mono text-accent">{telephonyMsg}</p>
            )}
          </div>
        </div>
      </DevCard>

      <DevCard delayMs={0}>
        <div className="space-y-4">
          <div>
            <h2 className="text-base font-semibold text-text">Live phone AI (speech-to-speech)</h2>
            <p className="text-sm text-text-muted mt-1">
              One stack for every SaaS tenant on PSTN and browser practice. Subscribers choose script, language, and
              voice slug only — not STT/LLM/TTS tiers. Persisted to{" "}
              <span className="font-mono text-xs">data/saas_universal_phone_stack.json</span>.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => selectProvider("openai")}
              className={`rounded-xl border p-4 text-left transition-colors ${
                !isGemini
                  ? "border-accent bg-accent/10 ring-1 ring-accent/30"
                  : "border-border bg-surface hover:border-accent/40"
              }`}
            >
              <p className="text-sm font-semibold text-text">OpenAI Realtime</p>
              <p className="text-xs text-text-muted mt-1">gpt-realtime-* · 24 kHz PCM · OpenAI voice slugs</p>
              <p className="mt-2 text-[11px] font-mono">
                {openaiReady ? "✓ API key configured" : "⚠ OPENAI_API_KEY missing"}
              </p>
            </button>
            <button
              type="button"
              onClick={() => selectProvider("gemini")}
              className={`rounded-xl border p-4 text-left transition-colors ${
                isGemini
                  ? "border-accent bg-accent/10 ring-1 ring-accent/30"
                  : "border-border bg-surface hover:border-accent/40"
              }`}
            >
              <p className="text-sm font-semibold text-text">Gemini Live</p>
              <p className="text-xs text-text-muted mt-1">gemini-*-live · 16 kHz in / 24 kHz out · mapped voices</p>
              <p className="mt-2 text-[11px] font-mono">
                {geminiReady
                  ? "✓ ENABLE_GEMINI + API key"
                  : !credentials?.gemini?.enabled
                    ? "⚠ ENABLE_GEMINI is false"
                    : "⚠ GEMINI_API_KEY missing"}
              </p>
            </button>
          </div>

          {catalogError && <p className="text-xs text-status-warning">{catalogError}</p>}

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm">
              <span className="text-text-muted">Realtime model</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm font-mono"
                value={
                  isRealtimeSpeechToSpeechModel(form.llmModel) ? form.llmModel : "gpt-realtime-2.1-mini"
                }
                onChange={(e) => {
                  const llmModel = e.target.value;
                  const row = speechModels.find((m) => m.id === llmModel);
                  patch({ llmModel, llmProvider: row?.provider || "openai" });
                }}
                disabled={catalogLoading}
              >
                {speechModels.map((m) => (
                  <option key={`${m.provider}:${m.id}`} value={m.id}>
                    {m.provider === "gemini" ? "Gemini" : "OpenAI"} — {m.label || m.id}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Default call language</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.language}
                onChange={(e) => patch({ language: e.target.value })}
              >
                {SAAS_PHONE_LANGUAGES.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label} ({l.id})
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Realtime voice (console slug)</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.realtimeVoice || DEFAULT_REALTIME_VOICE}
                onChange={(e) => patch({ realtimeVoice: e.target.value })}
              >
                {REALTIME_VOICE_OPTIONS.map((v) => (
                  <option key={v.id} value={v.id}>
                    {realtimeVoiceOptionLabel(v.id, { geminiLive: isGemini })}
                  </option>
                ))}
              </select>
              {isGemini && (
                <p className="mt-1 text-[11px] text-text-subtle">
                  PSTN maps to Gemini voice{" "}
                  <span className="font-mono">{geminiMappedVoice(form.realtimeVoice)}</span> on connect.
                </p>
              )}
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Turn detection</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.realtimeTurnDetection}
                onChange={(e) => patch({ realtimeTurnDetection: e.target.value })}
              >
                {REALTIME_TURN_DETECTION.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">VAD eagerness</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.realtimeVadEagerness}
                onChange={(e) => patch({ realtimeVadEagerness: e.target.value })}
              >
                {REALTIME_VAD_EAGERNESS.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Noise reduction (PSTN)</span>
              <select
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.realtimeNoiseReduction}
                onChange={(e) => patch({ realtimeNoiseReduction: e.target.value })}
              >
                {REALTIME_NOISE_REDUCTION.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Speech speed</span>
              <input
                type="number"
                step={0.05}
                min={0.25}
                max={1.5}
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={normalizeRealtimeSpeed(form.realtimeSpeed)}
                onChange={(e) => patch({ realtimeSpeed: Number(e.target.value) })}
              />
            </label>

            <label className="block text-sm">
              <span className="text-text-muted">Silence ms (server VAD)</span>
              <input
                type="number"
                step={50}
                min={200}
                max={2000}
                className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={form.realtimeSilenceMs ?? 250}
                onChange={(e) => patch({ realtimeSilenceMs: Number(e.target.value) })}
              />
            </label>
          </div>

          <div className="rounded-xl border border-border bg-surface-panel-inset p-4 space-y-3">
            <div>
              <p className="text-sm font-semibold text-text">Transcription (one mode)</p>
              <p className="text-xs text-text-muted mt-1">
                Pick live or post-call — not both. Usage per turn bills only the selected mode. Off = voice-only, no
                transcript add-on line items.
              </p>
            </div>
            {(
              [
                {
                  id: "off" as const,
                  title: "Off",
                  detail: "No transcript add-on; live model tokens only.",
                },
                {
                  id: "live" as const,
                  title: "Live — gpt-4o-mini-transcribe",
                  detail: "~$0.003/min. OpenAI Realtime: session STT. Gemini PSTN: parallel caller STT on inbound audio.",
                },
                {
                  id: "post_call" as const,
                  title: "Post-call — Gemini 3.5 Transcribe",
                  detail: "~$0.009/min after hangup (Telnyx recording). History modal when complete. Gemini PSTN only.",
                },
              ] as const
            ).map((opt) => (
              <label key={opt.id} className="flex items-start gap-3 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="transcriptionMode"
                  className="mt-1"
                  checked={(form.transcriptionMode || "off") === opt.id}
                  onChange={() => patch({ transcriptionMode: opt.id })}
                />
                <span>
                  <span className="font-medium text-text">{opt.title}</span>
                  <span className="block text-xs text-text-muted">{opt.detail}</span>
                </span>
              </label>
            ))}
          </div>

          {(warnings.length > 0 || adjustments.length > 0) && (
            <div className="rounded-xl border border-border bg-surface-panel-inset p-3 space-y-2">
              {warnings.map((w) => (
                <p key={w} className="text-xs text-status-warning">⚠ {w}</p>
              ))}
              {adjustments.map((a) => (
                <p key={a} className="text-xs text-text-muted">↳ Normalized: {a}</p>
              ))}
            </div>
          )}

          {alignment?.notes && alignment.notes.length > 0 && (
            <div className="skeuo-inset rounded-lg p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">PSTN alignment</p>
              <p className="mt-1 font-mono text-[11px] text-text">
                {alignment.liveProvider}/{alignment.liveModel} · voice {alignment.realtimeVoice} ·{" "}
                {alignment.language}
              </p>
              <ul className="mt-2 list-disc pl-4 text-[11px] text-text-muted space-y-1">
                {alignment.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="skeuo-inset rounded-lg p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Resolved dial override</p>
            <pre className="mt-2 max-h-40 overflow-auto font-mono text-[10px] text-text-muted whitespace-pre-wrap">
              {JSON.stringify(resolved || previewOverride, null, 2)}
            </pre>
          </div>

          <div>
            <button
              type="button"
              className="text-xs text-accent underline-offset-2 hover:underline"
              onClick={() => setShowJson((v) => !v)}
            >
              {showJson ? "Hide" : "Show"} advanced JSON
            </button>
            {showJson && (
              <textarea
                className="mt-2 w-full min-h-[180px] rounded-xl border border-border bg-surface p-3 font-mono text-xs"
                value={jsonEditor}
                onChange={(e) => setJsonEditor(e.target.value)}
                spellCheck={false}
              />
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" onClick={save}>Save universal stack</Button>
            <Button type="button" variant="secondary" onClick={load}>Reload</Button>
            {status && <span className="text-xs text-text-muted">{status}</span>}
          </div>
        </div>
      </DevCard>
    </div>
  );
}
