"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoEmptyState } from "@/components/ui/skeuo/SkeuoEmptyState";
import type { CallListItem } from "@/lib/call-list-utils";
import { CallListRow } from "@/components/calls/CallListRow";

export function CallsListPanel({
  calls,
  selectedId,
  onSelect,
  loading,
}: {
  calls: CallListItem[];
  selectedId: string | null;
  onSelect: (callId: string) => void;
  loading?: boolean;
}) {
  return (
    <SkeuoPanel
      title="Call archive"
      description="Primary unit of review — select a row to inspect"
      padding="md"
      className="min-h-[420px]"
    >
      {loading && calls.length === 0 ? (
        <p className="text-sm text-text-muted">Loading call archive…</p>
      ) : calls.length === 0 ? (
        <SkeuoEmptyState
          title="No calls yet"
          body="Start a voice session in Test Studio to create your first durable call record."
          actionHref="/app/test-studio"
          actionLabel="Start voice test"
        />
      ) : (
        <ul className="space-y-2 max-h-[min(70vh,640px)] overflow-y-auto pr-1">
          {calls.map((call) => (
            <li key={call.call_id}>
              <CallListRow
                call={call}
                selected={selectedId === call.call_id}
                onSelect={() => onSelect(call.call_id)}
              />
            </li>
          ))}
        </ul>
      )}
    </SkeuoPanel>
  );
}
