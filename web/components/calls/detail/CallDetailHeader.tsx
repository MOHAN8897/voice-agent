"use client";

import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";
import type { CallMeta, OutcomePayload } from "@/lib/call-detail-types";
import { formatDuration } from "@/lib/call-list-utils";

export function CallDetailHeader({
  meta,
  outcome,
}: {
  meta: CallMeta;
  outcome: OutcomePayload | null;
}) {
  const disposition = outcome?.disposition || meta.disposition || "pending";
  const tier = (meta.tier || "—").toUpperCase();

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
        <span>{formatDuration(meta.duration_sec)}</span>
        <span>{meta.channel || "—"}</span>
        <span>{meta.environment || "—"}</span>
      </div>
    </header>
  );
}
