"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import {
  PSTN_LIFECYCLE_STEPS,
  stageIndex,
  type PstnLifecycleStage,
} from "@/lib/pstn-lifecycle";

export type { PstnLifecycleStage };
export { mapProviderStatus, advanceLifecycle } from "@/lib/pstn-lifecycle";

export function PstnCallStatusTimeline({
  stage,
  placedAt,
  sessionClockMs = 0,
}: {
  stage: PstnLifecycleStage;
  placedAt?: number | null;
  sessionClockMs?: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  const frozenMsRef = useRef<number | null>(null);

  useEffect(() => {
    if (stage === "idle") {
      frozenMsRef.current = null;
      return;
    }
    if (stage === "hangup") {
      if (frozenMsRef.current == null) {
        frozenMsRef.current =
          placedAt != null ? Math.max(0, Date.now() - placedAt) : sessionClockMs;
      }
      return;
    }
    frozenMsRef.current = null;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [stage, placedAt, sessionClockMs]);

  const activeIdx = stageIndex(stage);
  const liveMs =
    stage === "hangup"
      ? frozenMsRef.current ?? sessionClockMs
      : placedAt != null && stage !== "idle"
        ? Math.max(0, now - placedAt)
        : sessionClockMs;
  const clock =
    liveMs > 0
      ? `${String(Math.floor(liveMs / 60000)).padStart(2, "0")}:${String(
          Math.floor((liveMs / 1000) % 60),
        ).padStart(2, "0")}`
      : "00:00";

  return (
    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4" data-testid="pstn-call-timeline">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Live call timeline</p>
          <p className="mt-1 text-sm text-text-muted">
            {stage === "idle"
              ? "Place a call to start the session clock and usage meter."
              : `Session clock ${clock}${placedAt ? ` · started ${new Date(placedAt).toLocaleTimeString()}` : ""}`}
          </p>
        </div>
        {stage !== "idle" && (
          <span
            className={cn(
              "rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-wider",
              stage === "hangup"
                ? "bg-surface-raised text-text-muted"
                : stage === "closing"
                  ? "bg-accent/15 text-accent"
                  : "bg-accent/15 text-accent animate-pulse",
            )}
          >
            {stage === "hangup" ? "Ended" : stage === "closing" ? "Closing" : "Live"}
          </span>
        )}
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-6">
        {PSTN_LIFECYCLE_STEPS.map((step, i) => {
          const done = activeIdx > i;
          const current = activeIdx === i;
          return (
            <li
              key={step.id}
              data-testid={`pstn-lifecycle-${step.id}`}
              data-state={current ? "current" : done ? "done" : "pending"}
              aria-current={current ? "step" : undefined}
              className={cn(
                "relative rounded-lg border px-3 py-2 text-center transition-colors",
                current
                  ? stage === "hangup"
                    ? "border-text-muted bg-surface-raised shadow-[0_0_0_1px_rgba(255,255,255,0.06)]"
                    : "border-status-live bg-status-live/15 shadow-[0_0_0_1px_rgba(225,29,72,0.45)]"
                  : done
                    ? "border-success/30 bg-success/10"
                    : "border-surface-border-subtle bg-surface-panel-inset opacity-55",
              )}
            >
              {current ? (
                <span
                  className={cn(
                    "absolute right-2 top-2 h-1.5 w-1.5 rounded-full",
                    stage === "hangup" ? "bg-text-muted" : "bg-status-live animate-pulse",
                  )}
                  aria-hidden
                />
              ) : null}
              <p
                className={cn(
                  "text-[10px] font-semibold uppercase tracking-wide",
                  current ? "text-text" : done ? "text-text" : "text-text-subtle",
                )}
              >
                {step.label}
              </p>
              <p className="mt-1 text-[9px] leading-snug text-text-subtle">{step.hint}</p>
              {current ? (
                <p className="mt-1 font-mono text-[8px] uppercase tracking-wider text-status-live">
                  {stage === "hangup" ? "Current" : "Active"}
                </p>
              ) : done ? (
                <p className="mt-1 font-mono text-[8px] uppercase tracking-wider text-success">Done</p>
              ) : (
                <p className="mt-1 font-mono text-[8px] uppercase tracking-wider text-text-subtle">Waiting</p>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
