"use client";

import Link from "next/link";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";
import {
  type CallListItem,
  callCustomerLabel,
  formatDuration,
  formatCallTime,
} from "@/lib/call-list-utils";

export function CallDetailInspector({ call }: { call: CallListItem | null }) {
  if (!call) {
    return (
      <SkeuoPanel
        title="Detail inspector"
        description="Investigation workspace — transcript, audio, memory, trace"
        padding="md"
        className="min-h-[420px]"
      >
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Inspector idle</p>
          <p className="mt-2 max-w-sm text-sm text-text-muted">
            Select a call from the archive to open the full investigation console.
          </p>
        </div>
      </SkeuoPanel>
    );
  }

  return (
    <SkeuoPanel
      title="Detail inspector"
      description="Unified per-call debugging across STT, LLM, TTS, and memory"
      padding="md"
      className="min-h-[420px]"
      headerAction={
        <Link href={`/app/calls/${call.call_id}`}>
          <SkeuoButton variant="secondary" size="sm">Full workspace</SkeuoButton>
        </Link>
      }
    >
      <header className="skeuo-inset rounded-skeuo-md border border-surface-border-subtle p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Call investigation</p>
            <p className="mt-1 font-mono text-xs text-text break-all">{call.call_id}</p>
          </div>
          <StatusBadge tone={dispositionTone(call.disposition)}>
            {call.disposition || "pending"}
          </StatusBadge>
        </div>
        <div className="mt-3 flex flex-wrap gap-3 font-mono text-[10px] uppercase tracking-wider text-text-subtle">
          <span>{call.tier?.toUpperCase() || "—"} tier</span>
          <span>{formatDuration(call.duration_sec)}</span>
          <span>{call.channel || "—"}</span>
          <span>{formatCallTime(call.started_at)}</span>
        </div>
        <p className="mt-2 text-sm text-text">{callCustomerLabel(call)}</p>
      </header>

      <div className="mt-4">
        <CallDetailView callId={call.call_id} variant="inspector" />
      </div>
    </SkeuoPanel>
  );
}
