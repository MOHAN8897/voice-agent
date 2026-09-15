"use client";

import { useEffect, useMemo, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import type { CallDetailData, MemoryEvent } from "@/lib/call-detail-types";
import { buildUnifiedTimeline } from "@/lib/call-timeline-utils";
import { CallDetailHeader } from "@/components/calls/detail/CallDetailHeader";
import { CallOutcomePanel } from "@/components/calls/detail/CallOutcomePanel";
import { CallAudioPanel } from "@/components/calls/detail/CallAudioPanel";
import { CallTranscriptTimeline } from "@/components/calls/detail/CallTranscriptTimeline";
import { CallUnifiedTimeline } from "@/components/calls/detail/CallUnifiedTimeline";
import { CallMemoryStatePanel } from "@/components/calls/detail/CallMemoryStatePanel";
import { CallTraceLatencyPanel, CallTracePanel } from "@/components/calls/detail/CallTracePanel";
import { CallMetadataPanel } from "@/components/calls/detail/CallMetadataPanel";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

async function loadCallDetail(callId: string): Promise<CallDetailData> {
  const [metaR, txR, memR, outR, traceR, eventsR] = await Promise.all([
    fetch(`/api/call/${callId}`, { credentials: "include" }),
    fetch(`/api/call/${callId}/transcript`, { credentials: "include" }),
    fetch(`/api/call/${callId}/memory`, { credentials: "include" }),
    fetch(`/api/call/${callId}/outcome`, { credentials: "include" }),
    fetch(`/api/call/${callId}/trace`, { credentials: "include" }),
    fetch(`/api/call/${callId}/memory-events`, { credentials: "include" }),
  ]);

  if (!metaR.ok) throw new Error("Call not found");

  const meta = await metaR.json();
  const transcript = txR.ok
    ? ensureArray<CallDetailData["transcript"][number]>((await txR.json()).lines)
    : [];
  const memory = memR.ok ? ((await memR.json()).memory as CallDetailData["memory"]) || {} : {};
  const outcome = outR.ok ? ((await outR.json()).outcome as CallDetailData["outcome"]) : null;
  const trace = traceR.ok ? await traceR.json() : { turns: [] };
  const memoryEvents = eventsR.ok
    ? ensureArray<MemoryEvent>((await eventsR.json()).events)
    : [];

  return { meta, transcript, memory, outcome, trace, memoryEvents };
}

function shouldPollCallDetail(data: CallDetailData): boolean {
  const status = String(data.meta.finalization?.status || data.meta.finalization_status || "");
  const audio = String(data.meta.finalization?.audio || "");
  const mixReady = Boolean(data.meta.audio?.mix);
  return (
    status === "processing" ||
    status === "finalizing" ||
    audio === "pending" ||
    audio === "processing" ||
    !mixReady
  );
}

export function CallInvestigationConsole({ callId }: { callId: string }) {
  const [data, setData] = useState<CallDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setLoading(true);
    setError(null);

    const run = async (attempt: number) => {
      try {
        const d = await loadCallDetail(callId);
        if (cancelled) return;
        setData(d);
        setError(null);
        setLoading(false);
        if (shouldPollCallDetail(d) && attempt < 15) {
          timer = setTimeout(() => {
            void run(attempt + 1);
          }, 800);
        }
      } catch (e) {
        if (cancelled) return;
        if (attempt < 8) {
          timer = setTimeout(() => {
            void run(attempt + 1);
          }, 800);
          return;
        }
        setError(e instanceof Error ? e.message : "Failed to load call");
        setLoading(false);
      }
    };

    void run(0);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [callId]);

  const timelineEvents = useMemo(() => {
    if (!data) return [];
    return buildUnifiedTimeline(data.transcript, data.trace.turns || [], data.memoryEvents);
  }, [data]);

  if (loading) {
    return (
      <SkeuoPanel title="Loading investigation console" padding="lg">
        <p className="text-sm text-text-muted">Fetching transcript, trace, memory, and outcome…</p>
      </SkeuoPanel>
    );
  }

  if (error || !data) {
    return (
      <SkeuoPanel title="Call unavailable" padding="lg">
        <p className="text-sm text-status-error">{error || "Call not found"}</p>
      </SkeuoPanel>
    );
  }

  return (
    <div className="space-y-6 console-page-enter">
      <CallDetailHeader meta={data.meta} outcome={data.outcome} />

      <div className="grid gap-6 lg:grid-cols-2">
        <CallOutcomePanel outcome={data.outcome} />
        <CallAudioPanel callId={callId} preferClearAudio />
      </div>

      <CallTranscriptTimeline lines={data.transcript} />

      <CallUnifiedTimeline events={timelineEvents} />

      <div className="grid gap-6 lg:grid-cols-2">
        <CallTraceLatencyPanel trace={data.trace} />
        <CallTracePanel trace={data.trace} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <CallMemoryStatePanel memory={data.memory} events={data.memoryEvents} />
        <CallMetadataPanel meta={data.meta} />
      </div>
    </div>
  );
}
