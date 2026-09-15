"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { cn } from "@/lib/cn";
import type { MemorySnapshot, OutcomePayload, TranscriptLine } from "@/lib/call-detail-types";
import { CallAudioPanel } from "@/components/calls/detail/CallAudioPanel";
import { CallOutcomePanel } from "@/components/calls/detail/CallOutcomePanel";

/** Compact tabs for the Calls list detail inspector (split view). */
export function CallDetailInspectorTabs({ callId }: { callId: string }) {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [tab, setTab] = useState<"recording" | "transcript" | "memory" | "outcome">("recording");
  const [memory, setMemory] = useState<MemorySnapshot>({});
  const [outcome, setOutcome] = useState<OutcomePayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [txR, memR, outR] = await Promise.all([
        fetch(`/api/call/${callId}/transcript`, { credentials: "include" }),
        fetch(`/api/call/${callId}/memory`, { credentials: "include" }),
        fetch(`/api/call/${callId}/outcome`, { credentials: "include" }),
      ]);
      if (cancelled) return;
      if (txR.ok) {
        const tx = await txR.json();
        setLines(ensureArray<TranscriptLine>(tx.lines));
      }
      if (memR.ok) {
        const mem = await memR.json();
        setMemory((mem.memory as MemorySnapshot) || {});
      }
      if (outR.ok) {
        const out = await outR.json();
        setOutcome((out.outcome as OutcomePayload) || null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [callId]);

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {(["recording", "transcript", "memory", "outcome"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={cn(
              "rounded-skeuo-sm px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all",
              tab === name ? "skeuo-btn-primary text-white" : "skeuo-btn-secondary text-text-muted"
            )}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "recording" && (
        <div className="mt-4">
          <CallAudioPanel callId={callId} preferClearAudio />
        </div>
      )}

      {tab === "transcript" && (
        <div className="mt-4">
          <ul className="space-y-2 max-h-64 overflow-y-auto">
            {lines.length === 0 ? (
              <li className="text-sm text-text-muted">No transcript lines yet.</li>
            ) : (
              lines.map((l, i) => (
                <li
                  key={i}
                  className={cn(
                    "rounded-skeuo-sm border px-3 py-2 text-sm",
                    l.role === "user"
                      ? "border-surface-border-subtle skeuo-inset"
                      : "border-accent-primary/15 bg-accent-primary/5"
                  )}
                >
                  <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{l.role}</span>
                  <p className="mt-1 text-text">{l.text}</p>
                </li>
              ))
            )}
          </ul>
        </div>
      )}

      {tab === "memory" && (
        <pre className="mt-4 max-h-64 overflow-auto rounded-skeuo-sm skeuo-inset p-3 font-mono text-xs text-text-muted">
          {JSON.stringify(memory, null, 2)}
        </pre>
      )}

      {tab === "outcome" && (
        <div className="mt-4">
          {outcome ? (
            <CallOutcomePanel outcome={outcome} />
          ) : (
            <p className="text-sm text-text-muted">Outcome pending or not generated yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
