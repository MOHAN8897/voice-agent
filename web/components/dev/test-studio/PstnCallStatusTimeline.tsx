"use client";

import { cn } from "@/lib/cn";

export type PstnLifecycleStage =
  | "idle"
  | "placed"
  | "ringing"
  | "lifted"
  | "ongoing"
  | "closing"
  | "hangup";

const STEPS: { id: PstnLifecycleStage; label: string; hint: string }[] = [
  { id: "placed", label: "Call placed", hint: "Outbound dial accepted by provider" },
  { id: "ringing", label: "Ringing", hint: "Callee phone is ringing" },
  { id: "lifted", label: "Call lifted", hint: "Callee answered — media stream starting" },
  { id: "ongoing", label: "In progress", hint: "Agent and caller are connected" },
  { id: "closing", label: "Closing", hint: "Playing farewell — short pause, then disconnect" },
  { id: "hangup", label: "Hangup", hint: "Call ended — finalizing recording and cost" },
];

function stageIndex(stage: PstnLifecycleStage): number {
  if (stage === "idle") return -1;
  return STEPS.findIndex((s) => s.id === stage);
}

export function mapProviderStatus(status?: string, hasInternal?: boolean): PstnLifecycleStage {
  const st = (status || "").toLowerCase();
  if (!st || st === "idle") return "idle";
  if (["completed", "failed", "busy", "no-answer", "canceled", "hangup"].includes(st)) return "hangup";
  if (st === "closing" || st === "hangup_closing") return "closing";
  if (hasInternal || st === "streaming" || st === "in-progress" || st === "active") return "ongoing";
  if (st === "answered") return "lifted";
  if (st === "ringing" || st === "initiated") return st === "ringing" ? "ringing" : "placed";
  return "placed";
}

export function PstnCallStatusTimeline({
  stage,
  placedAt,
  sessionClockMs = 0,
}: {
  stage: PstnLifecycleStage;
  placedAt?: number | null;
  sessionClockMs?: number;
}) {
  const activeIdx = stageIndex(stage);
  const clock =
    sessionClockMs > 0
      ? `${String(Math.floor(sessionClockMs / 60000)).padStart(2, "0")}:${String(
          Math.floor((sessionClockMs / 1000) % 60)
        ).padStart(2, "0")}`
      : "00:00";

  return (
    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4">
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
                  : "bg-accent/15 text-accent animate-pulse"
            )}
          >
            {stage === "hangup" ? "Ended" : stage === "closing" ? "Closing" : "Live"}
          </span>
        )}
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-6">
        {STEPS.map((step, i) => {
          const done = activeIdx > i || (stage === "hangup" && i <= STEPS.length - 1);
          const current = activeIdx === i && stage !== "hangup";
          return (
            <li
              key={step.id}
              className={cn(
                "rounded-lg border px-3 py-2 text-center transition-colors",
                done && !current
                  ? "border-success/30 bg-success/10"
                  : current
                    ? "border-accent/40 bg-accent/10"
                    : "border-surface-border-subtle bg-surface-panel-inset"
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-text">{step.label}</p>
              <p className="mt-1 text-[9px] leading-snug text-text-subtle">{step.hint}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
