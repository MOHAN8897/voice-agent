"use client";

import { useEffect, useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { cn } from "@/lib/cn";

type Finalization = {
  status?: string;
  ledger?: string;
  audio?: string;
  outcome?: string;
  components?: Record<string, string>;
};

const LIFECYCLE_STEPS = [
  { key: "active", label: "Active call", field: null },
  { key: "ledger", label: "Transcript seal", field: "ledger" },
  { key: "audio", label: "Audio archive", field: "audio" },
  { key: "outcome", label: "Outcome LLM", field: "outcome" },
] as const;

export function TestStudioLifecycle({
  callId,
  channel,
  ended,
}: {
  callId: string | null;
  channel: "agent" | "pstn";
  ended: boolean;
}) {
  const [fin, setFin] = useState<Finalization | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!callId) {
      setFin(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function load() {
      const r = await fetch(`/api/call/${callId}/finalization`, { credentials: "include" });
      if (!r.ok || cancelled) return;
      const j = await r.json();
      setFin(j);
      if (j.status === "complete" || j.status === "failed") {
        setPolling(false);
        if (timer) clearInterval(timer);
      }
    }

    load();
    if (ended) {
      setPolling(true);
      timer = setInterval(load, 2000);
    }

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [callId, ended]);

  const overall = fin?.status || (callId ? (ended ? "processing" : "active") : "idle");

  return (
    <SkeuoPanel title="Call lifecycle" description="Live session → archive → outcome" padding="md">
      <div className="flex flex-wrap items-center gap-2">
        <SkeuoBadge tone="info">{channel}</SkeuoBadge>
        <SkeuoBadge
          tone={
            overall === "complete" ? "success" : overall === "failed" ? "error" : overall === "active" ? "live" : "muted"
          }
        >
          {overall}
        </SkeuoBadge>
        {polling && <span className="text-xs text-text-subtle">polling…</span>}
      </div>
      {callId && (
        <p className="mt-2 font-mono text-[10px] text-text-subtle break-all">{callId}</p>
      )}

      <ol className="mt-4 space-y-2">
        {LIFECYCLE_STEPS.map((step, i) => {
          const compStatus =
            step.field
              ? fin?.[step.field as keyof Finalization] || fin?.components?.[step.field] || "pending"
              : null;
          const stepStatus =
            step.key === "active"
              ? callId && !ended
                ? "running"
                : callId
                  ? "done"
                  : "pending"
              : String(compStatus || "pending");
          return (
            <li
              key={step.key}
              className="flex items-center gap-3 rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 text-sm skeuo-inset"
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold",
                  stepStatus === "complete" || stepStatus === "done"
                    ? "bg-status-success/20 text-status-success"
                    : stepStatus === "running" || stepStatus === "processing"
                      ? "bg-accent-primary/20 text-accent-primary"
                      : stepStatus === "failed"
                        ? "bg-status-error/20 text-status-error"
                        : "bg-surface-panel-raised text-text-subtle"
                )}
              >
                {i + 1}
              </span>
              <p className="min-w-0 flex-1 font-medium text-text">{step.label}</p>
              <span className="font-mono text-[10px] uppercase text-text-subtle">{stepStatus}</span>
            </li>
          );
        })}
      </ol>
    </SkeuoPanel>
  );
}
