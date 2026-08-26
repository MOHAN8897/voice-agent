"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { CallMeta } from "@/lib/call-detail-types";
import { formatCallTime } from "@/lib/call-list-utils";

export function CallMetadataPanel({ meta }: { meta: CallMeta }) {
  const fin = meta.finalization || {};
  const stack = meta.resolved_stack || {};

  const rows: Array<{ label: string; value: string }> = [
    { label: "Agent", value: meta.agent_id || "—" },
    { label: "Channel", value: meta.channel || "—" },
    { label: "Direction", value: meta.direction || "—" },
    { label: "Tier", value: meta.tier || "—" },
    { label: "Environment", value: meta.environment || "—" },
    { label: "Started", value: formatCallTime(meta.started_at) },
    { label: "Ended", value: formatCallTime(meta.ended_at) },
    { label: "End reason", value: meta.end_reason || "—" },
    { label: "Combination", value: meta.combination_id || "—" },
    { label: "Brain version", value: meta.compiled_brain_version || "—" },
    { label: "Finalization", value: String(meta.finalization_status || fin.status || "—") },
    { label: "Ledger", value: String(fin.ledger || "—") },
    { label: "Audio archive", value: String(fin.audio || "—") },
    { label: "Outcome job", value: String(fin.outcome || "—") },
  ];

  return (
    <SkeuoPanel title="Metadata" description="Configuration snapshot and archive status" padding="md">
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.label} className="flex justify-between gap-3 text-sm border-b border-surface-border-subtle/60 pb-2">
            <span className="text-text-muted">{row.label}</span>
            <span className="font-mono text-xs text-text text-right break-all">{row.value}</span>
          </li>
        ))}
      </ul>

      {Object.keys(stack).length > 0 && (
        <div className="mt-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Resolved stack</p>
          <pre className="mt-2 max-h-40 overflow-auto rounded-skeuo-sm skeuo-inset p-3 font-mono text-[10px] text-text-muted">
            {JSON.stringify(stack, null, 2)}
          </pre>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <SkeuoBadge tone="muted">meta.json</SkeuoBadge>
        <SkeuoBadge tone="muted">trace.json</SkeuoBadge>
        <SkeuoBadge tone="muted">transcript.jsonl</SkeuoBadge>
        <SkeuoBadge tone="muted">outcome.json</SkeuoBadge>
      </div>
    </SkeuoPanel>
  );
}
