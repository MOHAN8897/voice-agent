"use client";

import { useEffect, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";

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

export function CallLifecyclePanel({
  callId,
  channel,
  ended,
}: {
  callId: string | null;
  channel: "browser" | "pstn";
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
    <DevCard title="Call lifecycle" description="Live session → archive → outcome">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full border border-surface-border px-2 py-0.5 font-mono uppercase text-text-muted">
          {channel}
        </span>
        {callId && (
          <span className="font-mono text-[10px] text-text-subtle truncate max-w-full">{callId}</span>
        )}
        <span
          className={`rounded-full px-2 py-0.5 font-semibold uppercase tracking-wider ${
            overall === "complete"
              ? "bg-success/15 text-success"
              : overall === "failed"
                ? "bg-red-500/15 text-red-300"
                : overall === "active"
                  ? "bg-accent/15 text-accent"
                  : "bg-surface-raised text-text-muted"
          }`}
        >
          {overall}
        </span>
        {polling && <span className="text-text-subtle">polling…</span>}
      </div>

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
              className="flex items-center gap-3 rounded-lg border border-surface-border-subtle px-3 py-2 text-sm"
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                  stepStatus === "complete" || stepStatus === "done"
                    ? "bg-success/20 text-success"
                    : stepStatus === "running" || stepStatus === "processing"
                      ? "bg-accent/20 text-accent"
                      : stepStatus === "failed"
                        ? "bg-red-500/20 text-red-300"
                        : "bg-surface-raised text-text-subtle"
                }`}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-text">{step.label}</p>
              </div>
              <span className="font-mono text-[10px] uppercase text-text-subtle">{stepStatus}</span>
            </li>
          );
        })}
      </ol>
    </DevCard>
  );
}
