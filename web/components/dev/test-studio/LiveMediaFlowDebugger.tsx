"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";

type Stage = {
  status?: "healthy" | "processing" | "delayed" | "failed";
  last_event_at?: number;
  codec?: string | null;
  sample_rate?: number | null;
  channels?: number | null;
  bytes?: number;
  frames?: number;
  duration_ms?: number;
  queue_size?: number;
  level_dbfs?: number | null;
  detail?: string | null;
};

type FlowEvent = Stage & {
  seq: number;
  timestamp: number;
  stage: string;
  direction: string;
  turn_id?: string | null;
  generation_id?: string | null;
  extra?: Record<string, unknown>;
};

type MediaFlow = {
  diagnostics?: {
    direction?: string;
    agent_id?: string;
    phase?: string;
    turn_id?: string;
    generation_id?: string;
    stt?: string;
    realtime?: string;
    model?: string;
    pipeline?: string;
    tts_provider?: string;
    tts_model?: string;
    tts_speaker?: string;
  };
  call_id?: string | null;
  external_id?: string | null;
  ws_id?: string | null;
  started_at?: number;
  updated_at?: number;
  active?: boolean;
  configured?: { codec: string; sample_rate: number; channels: number };
  negotiated?: { codec: string; sample_rate: number; channels: number };
  stages?: Record<string, Stage>;
  metrics?: {
    inbound_frames?: number;
    inbound_bytes?: number;
    outbound_generated_frames?: number;
    outbound_sent_frames?: number;
    outbound_bytes?: number;
    queue_size?: number;
    queue_duration_ms?: number;
    dropped_frames?: number;
    interrupted_frames?: number;
    inbound_packets_per_sec?: number;
    inbound_bytes_per_sec?: number;
    outbound_packets_per_sec?: number;
    outbound_bytes_per_sec?: number;
    normal_speech_dropped_frames?: number;
    barge_in_discarded_frames?: number;
    hangup_discarded_frames?: number;
    queue_high_watermark_events?: number;
    producer_backpressure_wait_count?: number;
    producer_backpressure_wait_ms?: number;
    playout_underrun_count?: number;
    playout_concealment_frames?: number;
    queue_depth_p50?: number;
    queue_depth_p95?: number;
    queue_depth_p99?: number;
    text_queued_count?: number;
  };
  latencies?: {
    stt_final_ms?: number | null;
    llm_first_token_ms?: number | null;
    tts_first_audio_ms?: number | null;
    tts_generation_lag_ms?: number | null;
    telnyx_first_outbound_ms?: number | null;
  };
  events?: FlowEvent[];
  health?: {
    score?: number;
    checks?: Record<string, boolean>;
    failures?: string[];
    claim?: string | null;
  };
};

const FILTERS = ["All", "Inbound", "STT", "LLM", "TTS", "Conversion", "Queue", "Outbound", "Hangup", "Errors"];
const STAGE_FILTER: Record<string, string[]> = {
  Inbound: ["inbound_audio"],
  STT: ["stt_audio", "stt_final"],
  LLM: ["llm_started", "llm_first_token", "llm_usage"],
  TTS: ["tts_started", "tts_audio"],
  Conversion: ["converter"],
  Queue: ["outbound_queued", "queue_cleared", "tts_text_queued"],
  Outbound: ["outbound_sent"],
  Hangup: ["hangup_closing", "hangup_complete", "fsm_phase"],
};

function latestDetail(events: FlowEvent[] | undefined, stages: string[]) {
  if (!events?.length) return "";
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (stages.includes(event.stage) && event.detail) return event.detail;
  }
  return "";
}

function age(ts?: number) {
  if (!ts) return "never";
  const ms = Math.max(0, Date.now() - ts * 1000);
  return ms < 1000 ? `${Math.round(ms)} ms ago` : `${(ms / 1000).toFixed(1)} s ago`;
}

function tone(status?: string) {
  if (status === "failed") return "border-danger/50 bg-danger/10 text-danger";
  if (status === "delayed") return "border-warning/50 bg-warning/10 text-warning";
  if (status === "processing") return "border-accent/50 bg-accent/10 text-accent";
  if (status === "healthy") return "border-success/50 bg-success/10 text-success";
  return "border-surface-border bg-surface-raised text-text-muted";
}

function Node({ label, stage }: { label: string; stage?: Stage }) {
  return (
    <div className={`min-w-36 rounded-xl border p-3 ${tone(stage?.status)}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
        <span aria-label={stage?.status || "not started"}>{stage ? "●" : "○"}</span>
      </div>
      <p className="mt-2 font-mono text-[11px] text-text">
        {stage?.codec || "—"} {stage?.sample_rate ? `· ${stage.sample_rate} Hz` : ""}
      </p>
      <p className="mt-1 text-[10px] text-text-subtle">Last event {age(stage?.last_event_at)}</p>
    </div>
  );
}

function queueStage(stage: Stage | undefined, size: number): Stage | undefined {
  if (!stage && size <= 0) return stage;
  const status =
    size >= 20 ? "failed" : size >= 16 ? "delayed" : size >= 10 ? "processing" : stage?.status || "healthy";
  return { ...(stage || {}), status };
}

function Level({ label, value }: { label: string; value?: number | null }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value + 60) * (100 / 60)));
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px] uppercase tracking-wider text-text-subtle">
        <span>{label}</span><span>{value == null ? "—" : `${value.toFixed(1)} dBFS`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-raised">
        <div className="h-full rounded-full bg-success transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function LiveMediaFlowDebugger({ callId }: { callId?: string | null }) {
  const [flow, setFlow] = useState<MediaFlow | null>(null);
  const [filter, setFilter] = useState("All");
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const query = callId ? `?call_id=${encodeURIComponent(callId)}` : "";
    try {
      const response = await portalFetch("dev", `/api/dev/telephony/media-flow${query}`);
      if (!response.ok) throw new Error(`Diagnostics unavailable (${response.status})`);
      const body = await response.json();
      setFlow(body.flow || null);
      setLoadError("");
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Diagnostics connection lost");
    }
  }, [callId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, 1000);
    return () => clearInterval(timer);
  }, [load]);

  const events = useMemo(() => {
    const all = [...(flow?.events || [])];
    if (filter === "All") return all;
    if (filter === "Errors") return all.filter((event) => event.status === "failed");
    const stages = STAGE_FILTER[filter] || [];
    return all.filter((event) => stages.includes(event.stage));
  }, [flow?.events, filter]);

  const textPipeline = useMemo(() => {
    const raw = flow?.events || [];
    return {
      stt: latestDetail(raw, ["stt_final"]),
      llmIn: latestDetail(raw, ["llm_started"]),
      tts: latestDetail(raw, ["tts_started"]),
    };
  }, [flow?.events]);

  async function diagnostic(path: "test-codec" | "test-audio" | "test-telnyx-speak" | "purge") {
    if (busy) return;
    setBusy(true);
    const labels = {
      "test-codec": "Testing codec paths…",
      "test-audio": "Sending known agent phrase…",
      "test-telnyx-speak": "Playing Telnyx native speak…",
      "purge": "Stopping playback…",
    };
    setMessage(labels[path]);
    const suffix = path !== "test-codec" && (flow?.external_id || callId)
      ? `?call_id=${encodeURIComponent(flow?.external_id || callId || "")}`
      : "";
    try {
      const response = await portalFetch("dev", `/api/dev/telephony/media-flow/${path}${suffix}`, { method: "POST" });
      const body = await response.json();
      setMessage(response.ok && body.ok ? (body.detail || "Diagnostic passed") : (body.error || body.detail || "Diagnostic failed"));
      await load();
    } catch {
      setMessage("Diagnostic request failed. Check the API connection and retry.");
    } finally {
      setBusy(false);
    }
  }

  const stages = flow?.stages || {};
  const metrics = flow?.metrics || {};
  const failures = flow?.health?.failures || [];
  const negotiated = flow?.negotiated;
  const configured = flow?.configured;
  const audioE2e = flow?.diagnostics?.pipeline === "realtime_voice";
  const mismatch = configured && negotiated && (
    configured.codec !== negotiated.codec ||
    configured.sample_rate !== negotiated.sample_rate ||
    configured.channels !== negotiated.channels
  );

  return (
    <DevCard title="Live call media flow" description="Actual negotiated bytes and runtime stages — not a handset audibility claim">
      {loadError ? <p role="alert" className="mb-3 text-sm text-danger">{loadError}. Displayed data may be stale.</p> : null}
      {!flow ? (
        <div className="rounded-xl border border-dashed border-surface-border p-6 text-sm text-text-muted">
          No media stream observed yet. Place and answer a Telnyx call.
        </div>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full border px-2 py-1 ${flow.active ? tone("healthy") : tone()}`}>
              {flow.active ? "LIVE" : "ENDED"}
            </span>
            <span className="font-mono text-text-muted">call {flow.call_id?.slice(0, 12) || "pending"}</span>
            <span className="font-mono text-text-subtle">ws {flow.ws_id}</span>
            <span className="text-text">{flow.diagnostics?.direction || "unknown direction"} · {flow.diagnostics?.phase || "connecting"}</span>
            <span className="ml-auto font-semibold text-text">Health {flow.health?.score ?? 0}%</span>
          </div>

          <dl className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-3 text-xs">
            <div><dt className="text-text-subtle">Agent</dt><dd className="break-all text-text">{flow.diagnostics?.agent_id || "pending"}</dd></div>
            <div><dt className="text-text-subtle">{audioE2e ? "Audio in" : "STT stream"}</dt><dd className="text-text">{flow.diagnostics?.stt || "unknown"}</dd></div>
            <div><dt className="text-text-subtle">Realtime</dt><dd className="text-text">{flow.diagnostics?.realtime || "unknown"} · {flow.diagnostics?.model || "—"}</dd></div>
            <div><dt className="text-text-subtle">{audioE2e ? "Audio out" : "TTS provider"}</dt><dd className="break-all text-text">{flow.diagnostics?.tts_provider || "—"} {flow.diagnostics?.tts_model ? `· ${flow.diagnostics.tts_model}` : ""} {flow.diagnostics?.tts_speaker ? `· ${flow.diagnostics.tts_speaker}` : ""}</dd></div>
            <div><dt className="text-text-subtle">Turn / generation</dt><dd className="break-all text-text">{flow.diagnostics?.turn_id || "—"} / {flow.diagnostics?.generation_id || "—"}</dd></div>
          </dl>

          {mismatch ? (
            <div className="rounded-xl border border-danger/50 bg-danger/10 px-4 py-3 text-sm text-danger">
              <strong>Negotiation mismatch:</strong> configured {configured?.codec}/{configured?.sample_rate} → actual{" "}
              {negotiated?.codec}/{negotiated?.sample_rate}. Explicit conversion is active.
            </div>
          ) : null}
          {failures.map((failure) => (
            <div key={failure} className="rounded-lg bg-danger/10 px-3 py-2 font-mono text-xs text-danger">{failure}</div>
          ))}

          <section aria-label="Text pipeline" className="rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-text-subtle">
              {audioE2e ? "Audio E2E · Telnyx PCM ↔ OpenAI Realtime" : "Text pipeline · what the agent processes"}
            </p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-accent">
                  {audioE2e ? "Caller transcript" : "STT heard (caller → text)"}
                </p>
                <p className="mt-2 min-h-12 rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-text">
                  {textPipeline.stt || "Waiting for caller speech…"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-warning">
                  {audioE2e ? "Realtime turn" : "LLM input (text → brain)"}
                </p>
                <p className="mt-2 min-h-12 rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-text">
                  {textPipeline.llmIn || "No turn started yet…"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-warning">
                  {audioE2e ? "Realtime audio out" : "TTS output (text → voice)"}
                </p>
                <p className="mt-2 min-h-12 rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-text">
                  {textPipeline.tts || (audioE2e ? "Waiting for OpenAI audio…" : "No agent speech queued yet…")}
                </p>
              </div>
            </div>
          </section>

          <section aria-label="Inbound audio flow">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-accent">Inbound · caller → agent</p>
            <div className="flex gap-2 overflow-x-auto pb-2">
              <Node label="PSTN caller" stage={stages.inbound_audio} />
              <span className="self-center text-accent">→</span>
              <Node label="Telnyx inbound" stage={stages.inbound_audio} />
              <span className="self-center text-accent">→</span>
              <Node label={audioE2e ? "16k → 24k PCM" : "PCM normalizer"} stage={stages.stt_audio} />
              <span className="self-center text-accent">→</span>
              <Node
                label={audioE2e ? "OpenAI audio in" : "Streaming STT"}
                stage={stages.stt_stream || stages.stt_final || stages.stt_audio}
              />
            </div>
          </section>

          <section aria-label="Outbound audio flow">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-warning">Outbound · agent → caller</p>
            <div className="flex gap-2 overflow-x-auto pb-2">
              <Node label={audioE2e ? "OpenAI Realtime" : "LLM"} stage={stages.llm_first_token || stages.llm_started} />
              <span className="self-center text-warning">→</span>
              <Node label={audioE2e ? "24k → 16k L16" : "TTS"} stage={stages.tts_audio || stages.tts_started} />
              <span className="self-center text-warning">→</span>
              <Node label="Converter" stage={stages.converter} />
              <span className="self-center text-warning">→</span>
              <Node label={`Queue · ${metrics.queue_size || 0}`} stage={queueStage(stages.outbound_queued, metrics.queue_size || 0)} />
              <span className="self-center text-warning">→</span>
              <Node label="Telnyx outbound" stage={stages.outbound_sent} />
              <span className="self-center text-warning">→</span>
              <Node label="PSTN caller" stage={stages.outbound_sent} />
            </div>
          </section>

          <div className="grid gap-3 sm:grid-cols-2">
            <Level label="Inbound level" value={stages.inbound_audio?.level_dbfs} />
            <Level label="Outbound level" value={stages.outbound_sent?.level_dbfs} />
          </div>

          <dl className="grid grid-cols-2 gap-3 rounded-xl border border-surface-border-subtle p-3 text-xs sm:grid-cols-4">
            <div><dt className="text-text-subtle">Inbound frames</dt><dd className="mt-1 font-mono text-text">{metrics.inbound_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">Outbound sent</dt><dd className="mt-1 font-mono text-text">{metrics.outbound_sent_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">Queue delay</dt><dd className="mt-1 font-mono text-text">{metrics.queue_duration_ms || 0} ms</dd></div>
            <div><dt className="text-text-subtle">Queue p95 / p99</dt><dd className="mt-1 font-mono text-text">{metrics.queue_depth_p95 || 0} / {metrics.queue_depth_p99 || 0}</dd></div>
            <div><dt className="text-text-subtle">Interrupted</dt><dd className="mt-1 font-mono text-text">{metrics.interrupted_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">Speech drops</dt><dd className="mt-1 font-mono text-text">{metrics.normal_speech_dropped_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">TTS text chunks</dt><dd className="mt-1 font-mono text-text">{metrics.text_queued_count || 0}</dd></div>
            <div><dt className="text-text-subtle">TTS generation lag</dt><dd className="mt-1 font-mono text-text">{flow.latencies?.tts_generation_lag_ms ?? "—"} ms</dd></div>
            <div><dt className="text-text-subtle">Barge discards</dt><dd className="mt-1 font-mono text-text">{metrics.barge_in_discarded_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">Backpressure waits</dt><dd className="mt-1 font-mono text-text">{metrics.producer_backpressure_wait_count || 0} · {metrics.producer_backpressure_wait_ms || 0} ms</dd></div>
            <div><dt className="text-text-subtle">Underruns</dt><dd className="mt-1 font-mono text-text">{metrics.playout_underrun_count || 0}</dd></div>
            <div><dt className="text-text-subtle">PLC silence</dt><dd className="mt-1 font-mono text-text">{metrics.playout_concealment_frames || 0}</dd></div>
            <div><dt className="text-text-subtle">Inbound rate</dt><dd className="mt-1 font-mono text-text">{metrics.inbound_packets_per_sec || 0} pkt/s</dd></div>
            <div><dt className="text-text-subtle">Outbound rate</dt><dd className="mt-1 font-mono text-text">{metrics.outbound_packets_per_sec || 0} pkt/s</dd></div>
            <div><dt className="text-text-subtle">LLM first token</dt><dd className="mt-1 font-mono text-text">{flow.latencies?.llm_first_token_ms ?? "—"} ms</dd></div>
            <div><dt className="text-text-subtle">TTS → Telnyx</dt><dd className="mt-1 font-mono text-text">{flow.latencies?.telnyx_first_outbound_ms ?? "—"} ms</dd></div>
          </dl>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" disabled={busy || !flow.active} onClick={() => diagnostic("test-audio")}>Test agent audio</Button>
            <Button type="button" variant="secondary" disabled={busy || !flow.active} onClick={() => diagnostic("test-telnyx-speak")}>Test Telnyx speak</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => diagnostic("test-codec")}>Test codec</Button>
            <Button type="button" variant="secondary" disabled={busy || !flow.active} onClick={() => diagnostic("purge")}>Purge playback</Button>
            {message ? <span role="status" className="self-center text-xs text-text-muted">{message}</span> : null}
          </div>

          <div>
            <div className="mb-3 flex gap-1 overflow-x-auto pb-1">
              {FILTERS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setFilter(item)}
                  aria-pressed={filter === item}
                  className={`rounded-lg px-2 py-1 text-[10px] font-medium ${filter === item ? "bg-accent/15 text-accent" : "text-text-subtle hover:bg-surface-raised"}`}
                >
                  {item}
                </button>
              ))}
            </div>
            <div className="max-h-72 space-y-1 overflow-y-auto rounded-xl bg-surface-raised p-2 font-mono text-[10px]">
              {events.slice(-100).map((event) => (
                <div key={event.seq} className={`grid grid-cols-[72px_minmax(0,1fr)] gap-2 rounded px-2 py-1.5 ${event.status === "failed" ? "bg-danger/10 text-danger" : "text-text-muted"}`}>
                  <span title={new Date(event.timestamp * 1000).toISOString()}>+{Math.round((event.timestamp - (flow.started_at || event.timestamp)) * 1000)} ms</span>
                  <span className="break-words text-text">{event.stage}</span>
                  <span className="col-span-2 break-words">
                    {event.detail ? (
                      <span className="text-text">{event.detail} · </span>
                    ) : null}
                    {event.codec || "—"} {event.sample_rate || "—"} Hz · {event.bytes || 0} B · q {event.queue_size || 0}
                  </span>
                </div>
              ))}
              {!events.length ? <p className="px-2 py-4 text-text-subtle">No matching events.</p> : null}
            </div>
          </div>
        </div>
      )}
    </DevCard>
  );
}
