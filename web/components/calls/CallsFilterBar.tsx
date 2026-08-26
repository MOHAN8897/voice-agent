"use client";

import { SkeuoInput } from "@/components/ui/skeuo/SkeuoInput";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

const DISPOSITIONS = [
  "new_lead",
  "interested",
  "qualified",
  "site_visit_planned",
  "callback_required",
  "not_interested",
  "wrong_number",
  "converted",
  "no_outcome",
] as const;

export type CallsFilters = {
  search: string;
  channel: string;
  disposition: string;
  since: string;
  until: string;
};

export function CallsFilterBar({
  filters,
  onChange,
  onApply,
  onReset,
  total,
  loading,
}: {
  filters: CallsFilters;
  onChange: (patch: Partial<CallsFilters>) => void;
  onApply: () => void;
  onReset: () => void;
  total: number;
  loading?: boolean;
}) {
  return (
    <SkeuoPanel
      title="Filter rack"
      description="Narrow the archive — disposition, channel, and time window"
      padding="md"
      headerAction={
        <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
          {loading ? "Scanning…" : `${total} calls`}
        </span>
      }
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))_auto] lg:items-end">
        <label className="block text-sm">
          <span className="text-text-muted">Search call ID</span>
          <SkeuoInput
            className="mt-0"
            placeholder="Partial UUID…"
            value={filters.search}
            onChange={(e) => onChange({ search: e.target.value })}
          />
        </label>

        <label className="block text-sm">
          <span className="text-text-muted">Channel</span>
          <select
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm"
            value={filters.channel}
            onChange={(e) => onChange({ channel: e.target.value })}
          >
            <option value="">All channels</option>
            <option value="browser">Browser</option>
            <option value="pstn">PSTN</option>
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-text-muted">Disposition</span>
          <select
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm"
            value={filters.disposition}
            onChange={(e) => onChange({ disposition: e.target.value })}
          >
            <option value="">All dispositions</option>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>{d.replace(/_/g, " ")}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-text-muted">Since</span>
          <SkeuoInput
            className="mt-0"
            type="date"
            value={filters.since}
            onChange={(e) => onChange({ since: e.target.value })}
          />
        </label>

        <label className="block text-sm">
          <span className="text-text-muted">Until</span>
          <SkeuoInput
            className="mt-0"
            type="date"
            value={filters.until}
            onChange={(e) => onChange({ until: e.target.value })}
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <SkeuoButton variant="primary" size="sm" onClick={onApply} loading={loading}>
            Apply
          </SkeuoButton>
          <SkeuoButton variant="ghost" size="sm" onClick={onReset}>
            Reset
          </SkeuoButton>
        </div>
      </div>
    </SkeuoPanel>
  );
}
