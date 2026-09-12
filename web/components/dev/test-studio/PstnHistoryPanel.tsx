"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { CallAudioPanel } from "@/components/calls/detail/CallAudioPanel";
import { CallMetadataPanel } from "@/components/calls/detail/CallMetadataPanel";
import { CallOutcomePanel } from "@/components/calls/detail/CallOutcomePanel";
import { CallTranscriptTimeline } from "@/components/calls/detail/CallTranscriptTimeline";
import { portalFetch } from "@/lib/auth-client";
import { ensureArray } from "@/lib/ensure-array";
import { formatDuration, pipelineLabel } from "@/lib/call-list-utils";
import { formatInr, formatUsd } from "@/lib/usage-cost";
import type { CallMeta, OutcomePayload, TranscriptLine } from "@/lib/call-detail-types";
import type { DevTelephonyHistoryRow } from "@/lib/dev-telephony-types";
import { callAudioUrl } from "@/lib/pstn-trace-metrics";
import { cn } from "@/lib/cn";

const PAGE_SIZE = 5;

function historyToMeta(row: DevTelephonyHistoryRow): CallMeta {
  const ledger = (row.ledger_meta || {}) as CallMeta;
  const usage = (ledger.usage || row.usage || {}) as CallMeta["usage"];
  return {
    ...ledger,
    agent_id: ledger.agent_id || row.agent_id,
    channel: ledger.channel || (row.pipeline === "realtime_voice" ? "pstn_realtime" : "pstn"),
    pipeline: ledger.pipeline || row.pipeline,
    caller_id: ledger.caller_id || row.to_e164,
    tier: ledger.tier || row.tier,
    duration_sec: ledger.duration_sec ?? row.duration_sec ?? undefined,
    started_at: ledger.started_at || row.placed_at,
    ended_at: ledger.ended_at || row.ended_at || undefined,
    direction: ledger.direction || row.direction || "outbound",
    end_reason: ledger.end_reason || row.cost?.end_reason,
    usage,
    cost_inr: row.cost?.cost_inr ?? ledger.cost_inr ?? usage?.cost_inr,
    cost_usd: row.cost?.cost_usd ?? ledger.cost_usd ?? usage?.cost_usd,
    cost_inr_per_min: row.cost?.cost_inr_per_min ?? ledger.cost_inr_per_min,
    model_cost_inr: row.cost?.model_cost_inr ?? ledger.model_cost_inr,
    telnyx_inr: row.cost?.telnyx_inr ?? ledger.telnyx_inr,
    resolved_stack: ledger.resolved_stack || row.meta?.stack_override,
  };
}

export function PstnHistoryPanel({
  agentId,
  onReviewCall,
  refreshKey = 0,
}: {
  agentId: string;
  onReviewCall?: (callId: string) => void;
  refreshKey?: number;
}) {
  const [rows, setRows] = useState<DevTelephonyHistoryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<DevTelephonyHistoryRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const q = new URLSearchParams({
      agent_id: agentId,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    const r = await portalFetch("dev", `/api/dev/telephony/history?${q.toString()}`);
    setLoading(false);
    if (!r.ok) return;
    const j = await r.json();
    setRows(ensureArray<DevTelephonyHistoryRow>(j.history));
    setTotal(Number(j.total || 0));
  }, [agentId, offset, refreshKey]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  async function openDetail(row: DevTelephonyHistoryRow) {
    setSelected(row);
    setDetailLoading(true);
    const r = await portalFetch("dev", `/api/dev/telephony/history/${row.history_id}`);
    setDetailLoading(false);
    if (!r.ok) return;
    const j = await r.json();
    setSelected((j.history as DevTelephonyHistoryRow) || row);
  }

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const transcript = ensureArray<TranscriptLine>(selected?.transcript);

  return (
    <>
      <DevCard title="Call history" description={`${PAGE_SIZE} per page · persisted across restarts · click a row for full session`}>
        <div className="overflow-x-auto rounded-xl border border-surface-border-subtle">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-surface-border-subtle bg-surface-raised text-xs text-text-muted">
              <tr>
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Route</th>
                <th className="px-3 py-2">Pipeline</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Duration</th>
                <th className="px-3 py-2">Model</th>
                <th className="px-3 py-2">Telnyx</th>
                <th className="px-3 py-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-3 py-4 text-text-muted">
                    Loading history…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-4 text-text-muted">
                    No persisted calls yet. Place an outbound test call to start history.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr
                    key={row.history_id}
                    data-testid="pstn-history-row"
                    className="cursor-pointer border-b border-surface-border-subtle/50 hover:bg-surface-raised"
                    onClick={() => void openDetail(row)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        void openDetail(row);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open call ${row.to_e164 || row.history_id}`}
                  >
                    <td className="px-3 py-2 font-mono text-[10px]">
                      {row.placed_at ? new Date(row.placed_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px]">
                      {row.from_e164 || "—"} → {row.to_e164 || "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">{pipelineLabel(row.pipeline, "pstn")}</td>
                    <td className="px-3 py-2 capitalize">{row.status || "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{formatDuration(row.duration_sec ?? undefined)}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {row.cost?.model_cost_inr != null ? formatInr(Number(row.cost.model_cost_inr)) : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {row.cost?.telnyx_inr != null ? formatInr(Number(row.cost.telnyx_inr)) : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {row.cost?.cost_inr != null ? formatInr(Number(row.cost.cost_inr)) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-text-muted">
            Page {page} of {pageCount} · {total} total
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={offset <= 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      </DevCard>

      {selected ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center"
          data-testid="pstn-history-detail"
          onClick={() => setSelected(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-surface-border bg-surface p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-text">Call session details</h3>
                <p className="font-mono text-[10px] text-text-subtle">{selected.history_id}</p>
                {detailLoading ? <p className="mt-1 text-xs text-text-muted">Loading ledger, transcript, and recording…</p> : null}
              </div>
              <Button type="button" variant="secondary" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>

            <section className="mt-4">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Session</p>
              <dl className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
                <MetaCell label="Provider" value={selected.provider || "—"} />
                <MetaCell label="Language" value={selected.language || "—"} />
                <MetaCell label="Tier" value={selected.tier || "—"} />
                <MetaCell label="Direction" value={selected.direction || "outbound"} />
                <MetaCell label="Route" value={`${selected.from_e164 || "—"} → ${selected.to_e164 || "—"}`} mono />
                <MetaCell label="Pipeline" value={pipelineLabel(selected.pipeline, "pstn")} />
                <MetaCell label="Status" value={selected.status || "—"} />
                <MetaCell label="Duration" value={formatDuration(selected.duration_sec ?? undefined)} />
                <MetaCell label="Placed" value={selected.placed_at ? new Date(selected.placed_at).toLocaleString() : "—"} />
                <MetaCell label="Answered" value={selected.answered_at ? new Date(selected.answered_at).toLocaleString() : "—"} />
                <MetaCell label="Ended" value={selected.ended_at ? new Date(selected.ended_at).toLocaleString() : "—"} />
                <MetaCell label="Internal call ID" value={selected.internal_call_id || "—"} mono />
                <MetaCell label="Provider call ID" value={selected.external_id || "—"} mono />
                <MetaCell label="Recording" value={selected.has_recording ? "Available" : "Pending or missing"} />
              </dl>
            </section>

            <div className="mt-4 rounded-xl border border-surface-border-subtle p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Cost breakdown</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <CostCell label="Model (LLM/STT/TTS)" inr={selected.cost?.model_cost_inr} usd={selected.cost?.model_cost_usd} />
                <CostCell label="Telnyx minutes" inr={selected.cost?.telnyx_inr} usd={selected.cost?.telnyx_usd} />
                <CostCell label="Total" inr={selected.cost?.cost_inr} usd={selected.cost?.cost_usd} accent />
              </div>
              {selected.cost?.cost_inr_per_min != null ? (
                <p className="mt-2 text-xs text-text-muted">
                  Effective rate {formatInr(Number(selected.cost.cost_inr_per_min))}/min
                </p>
              ) : null}
            </div>

            {selected.events && selected.events.length > 0 ? (
              <div className="mt-4">
                <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Timeline</p>
                <ol className="mt-2 space-y-1">
                  {selected.events.map((ev, i) => (
                    <li key={`${ev.at}-${i}`} className="flex gap-2 text-xs">
                      <span className="font-mono text-text-subtle">{new Date(ev.at).toLocaleTimeString()}</span>
                      <span className="font-semibold capitalize text-text">{ev.stage}</span>
                      {ev.detail ? <span className="text-text-muted">{ev.detail}</span> : null}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}

            {selected.internal_call_id ? (
              <div className="mt-4 space-y-4">
                <CallAudioPanel callId={selected.internal_call_id} preferClearAudio />
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={callAudioUrl(selected.internal_call_id, "mix_clear", true)}
                    className="rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-xs font-medium text-accent hover:bg-accent/15"
                  >
                    Download clear mix
                  </Link>
                  <Link
                    href={callAudioUrl(selected.internal_call_id, "mix", true)}
                    className="rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
                  >
                    Download raw mix
                  </Link>
                  <Link
                    href={callAudioUrl(selected.internal_call_id, "user_clear", true)}
                    className="rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
                  >
                    Download clear caller
                  </Link>
                  <Link
                    href={callAudioUrl(selected.internal_call_id, "agent_clear", true)}
                    className="rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
                  >
                    Download clear agent
                  </Link>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => onReviewCall?.(selected.internal_call_id!)}
                  >
                    Open review console
                  </Button>
                </div>
                <CallTranscriptTimeline lines={transcript} />
                <CallOutcomePanel outcome={(selected.outcome as OutcomePayload | null) || null} />
                <CallMetadataPanel meta={historyToMeta(selected)} />
              </div>
            ) : (
              <p className="mt-4 text-sm text-text-muted">
                Media stream never connected — no recording, transcript, or ledger metadata for this attempt.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

function MetaCell({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className={cn("mt-1 text-text break-all", mono ? "font-mono text-xs" : "text-sm")}>{value}</dd>
    </div>
  );
}

function CostCell({
  label,
  inr,
  usd,
  accent,
}: {
  label: string;
  inr?: number;
  usd?: number;
  accent?: boolean;
}) {
  return (
    <div className={cn("rounded-lg skeuo-inset px-3 py-2", accent && "border border-accent/20")}>
      <p className="font-mono text-[9px] uppercase text-text-subtle">{label}</p>
      <p className={cn("mt-1 font-mono text-sm font-semibold", accent ? "text-accent" : "text-text")}>
        {inr != null ? formatInr(Number(inr)) : "—"}
      </p>
      {usd != null ? <p className="font-mono text-[10px] text-text-muted">{formatUsd(Number(usd))}</p> : null}
    </div>
  );
}
