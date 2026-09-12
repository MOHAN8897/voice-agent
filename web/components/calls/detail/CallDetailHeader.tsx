"use client";

import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";
import type { CallMeta, OutcomePayload } from "@/lib/call-detail-types";
import { formatDuration, pipelineLabel } from "@/lib/call-list-utils";
import { formatInr, formatUsd } from "@/lib/usage-cost";

export function CallDetailHeader({
  meta,
  outcome,
}: {
  meta: CallMeta;
  outcome: OutcomePayload | null;
}) {
  const disposition = outcome?.disposition || meta.disposition || "pending";
  const tier = (meta.tier || "—").toUpperCase();
  const costInr = meta.cost_inr ?? meta.usage?.cost_inr;
  const costUsd = meta.cost_usd ?? meta.usage?.cost_usd;
  const modelInr = meta.model_cost_inr ?? meta.usage?.model_cost_inr;
  const telnyxInr = meta.telnyx_inr ?? meta.usage?.telnyx_inr;

  return (
    <header className="skeuo-panel rounded-skeuo-lg border border-surface-border-subtle p-5 console-page-enter">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Call investigation</p>
          <p className="mt-1 font-mono text-sm text-text break-all">{meta.call_id}</p>
        </div>
        <StatusBadge tone={dispositionTone(disposition)}>{disposition}</StatusBadge>
      </div>
      <div className="mt-4 flex flex-wrap gap-4 font-mono text-xs uppercase tracking-wider text-text-muted">
        <span>{tier} tier</span>
        <span>{formatDuration(meta.duration_sec ?? meta.usage?.duration_sec)}</span>
        <span>{pipelineLabel(meta.pipeline, meta.channel)}</span>
        <span>{meta.environment || "—"}</span>
        {modelInr != null && <span>model {formatInr(Number(modelInr))}</span>}
        {telnyxInr != null && <span>telnyx {formatInr(Number(telnyxInr))}</span>}
        {costInr != null && <span>total {formatInr(Number(costInr))}</span>}
        {costUsd != null && <span>{formatUsd(Number(costUsd))}</span>}
      </div>
    </header>
  );
}
