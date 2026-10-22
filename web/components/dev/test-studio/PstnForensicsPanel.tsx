"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";

type Forensics = {
  updated_at?: number;
  active?: boolean;
  ids?: Record<string, string | null | undefined>;
  carrier_leg?: Record<string, unknown>;
  timeline_ms_from_dial?: Record<string, number>;
  derived_ms?: Record<string, number | null | undefined>;
  playback?: Record<string, number | null | undefined>;
  runtime?: Record<string, unknown>;
  debug_hints?: string[];
  compare_recording?: { steps?: string[] };
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-surface-border-subtle/60 py-1.5 text-xs">
      <span className="text-text-muted">{label}</span>
      <span className="max-w-[65%] break-all text-right font-mono text-text">{value || "—"}</span>
    </div>
  );
}

export function PstnForensicsPanel({ callId }: { callId?: string | null }) {
  const [data, setData] = useState<Forensics | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const query = callId ? `?call_id=${encodeURIComponent(callId)}` : "";
    try {
      const res = await portalFetch("dev", `/api/dev/telephony/forensics${query}`);
      if (!res.ok) throw new Error(`Forensics unavailable (${res.status})`);
      const body = await res.json();
      setData(body.forensics || null);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Forensics failed");
    }
  }, [callId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [load]);

  async function copyJson() {
    if (!data) return;
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  }

  const ids = data?.ids || {};
  const leg = data?.carrier_leg || {};
  const timeline = data?.timeline_ms_from_dial || {};
  const derived = data?.derived_ms || {};
  const playback = data?.playback || {};
  const runtime = data?.runtime || {};

  return (
    <DevCard
      title="PSTN forensics"
      description="Request IDs, answer→audio timeline, carrier leg vs media, playback underruns — for manual call debugging"
    >
      {error ? <p className="mb-2 text-sm text-danger">{error}</p> : null}
      {!data ? (
        <p className="text-sm text-text-muted">Place or select a call to load forensics.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full border px-2 py-0.5 ${data.active ? "border-success/40 text-success" : "border-surface-border text-text-muted"}`}>
              {data.active ? "LIVE" : "ENDED / idle"}
            </span>
            <Button type="button" variant="secondary" className="!py-1.5 !px-3 text-xs" onClick={() => void copyJson()}>
              Copy JSON
            </Button>
            <Button type="button" variant="ghost" className="!py-1.5 !px-3 text-xs" onClick={() => void load()}>
              Refresh
            </Button>
          </div>

          <section>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">Correlation IDs</p>
            <Row label="Internal call ID" value={String(ids.call_id || "")} />
            <Row label="Telnyx control ID" value={String(ids.call_control_id || "")} />
            <Row label="Dial request ID" value={String(ids.dial_request_id || "")} />
            <Row label="Brain version" value={String(ids.compiled_brain_version || "")} />
            <Row label="Brain checksum" value={String(ids.brain_checksum || "").slice(0, 16)} />
            <Row label="Callee" value={String(ids.callee_e164 || "")} />
          </section>

          <section>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">
              Timeline (ms since dial initiated)
            </p>
            {Object.keys(timeline).length === 0 ? (
              <p className="text-xs text-text-muted">Waiting for initiated → answered → first outbound frame…</p>
            ) : (
              Object.entries(timeline).map(([k, v]) => <Row key={k} label={k} value={`${v} ms`} />)
            )}
            {derived.answer_to_first_audio_sent != null ? (
              <Row label="Answer → first sent (approx)" value={`${derived.answer_to_first_audio_sent} ms`} />
            ) : null}
          </section>

          <section>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">Carrier leg</p>
            <Row label="Leg status" value={String(leg.status || "")} />
            <Row label="Media status" value={String(leg.media_status || "")} />
            <Row label="Stream" value={String(leg.stream_state || "")} />
            <Row label="Last event" value={String(leg.last_event || "")} />
          </section>

          <section>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">Playback / interruptions</p>
            <Row label="Underruns" value={String(playback.playout_underrun_count ?? 0)} />
            <Row label="Outbound frames sent" value={String(playback.outbound_sent_frames ?? 0)} />
            <Row label="Barge discards" value={String(playback.barge_in_discarded_frames ?? 0)} />
            <Row label="Queue p95" value={String(playback.queue_depth_p95 ?? 0)} />
          </section>

          <section>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">Runtime</p>
            <Row label="Phase" value={String(runtime.phase || "")} />
            <Row label="Hangup source" value={String(runtime.hangup_arm_source || "")} />
            <Row label="Language" value={String(runtime.language || "")} />
            <Row label="Last caller text" value={String(runtime.last_user_final || "")} />
            <Row label="Pickup captured" value={String(runtime.pickup_text || "")} />
            {runtime.effective_vad ? (
              <pre className="mt-2 overflow-x-auto rounded-lg bg-surface-raised p-2 text-[10px] text-text-muted">
                {JSON.stringify(runtime.effective_vad, null, 2)}
              </pre>
            ) : null}
          </section>

          {(data.debug_hints || []).length > 0 && (
            <ul className="list-disc space-y-1 pl-4 text-xs text-warning">
              {data.debug_hints!.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}

          {data.compare_recording?.steps?.length ? (
            <section className="rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-3 text-xs text-text-muted">
              <p className="mb-2 font-semibold text-text">Recording comparison</p>
              <ol className="list-decimal space-y-1 pl-4">
                {data.compare_recording.steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </section>
          ) : null}
        </div>
      )}
    </DevCard>
  );
}
