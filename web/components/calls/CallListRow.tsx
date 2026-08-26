"use client";

import { cn } from "@/lib/cn";
import {
  type CallListItem,
  callCustomerLabel,
  callSummaryLine,
  formatCallTime,
  formatDuration,
} from "@/lib/call-list-utils";
import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";

export function CallListRow({
  call,
  selected,
  onSelect,
}: {
  call: CallListItem;
  selected?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full text-left rounded-skeuo-md border px-3 py-3 transition-all duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/35",
        selected
          ? "border-accent-primary/35 bg-accent-primary/8 skeuo-panel"
          : "border-surface-border-subtle skeuo-inset hover:border-accent-primary/20"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
            {formatCallTime(call.started_at)}
          </p>
          <p className="mt-1 truncate text-sm font-medium text-text">{callCustomerLabel(call)}</p>
        </div>
        <StatusBadge tone={dispositionTone(call.disposition)}>
          {call.disposition || "pending"}
        </StatusBadge>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <SkeuoBadge tone="muted">{call.channel || "—"}</SkeuoBadge>
        <SkeuoBadge tone="info">{call.tier?.toUpperCase() || "—"}</SkeuoBadge>
        <span className="font-mono text-[10px] text-text-subtle">{formatDuration(call.duration_sec)}</span>
      </div>

      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-text-muted">{callSummaryLine(call)}</p>
    </button>
  );
}
