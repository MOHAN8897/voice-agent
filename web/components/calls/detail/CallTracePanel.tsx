"use client";

import { useMemo } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import type { TracePayload, TraceTurn } from "@/lib/call-detail-types";
import { traceTurnLatencies } from "@/lib/call-timeline-utils";

function Bar({ label, ms, maxMs, tone }: { label: string; ms: number; maxMs: number; tone: string }) {
  const width = maxMs > 0 ? Math.min(100, Math.round((ms / maxMs) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between font-mono text-[10px] uppercase tracking-wider text-text-subtle">
        <span>{label}</span>
        <span>{ms > 0 ? `${ms}ms` : "—"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full skeuo-inset">
        <div className={cn("h-full rounded-full transition-all duration-300", tone)} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function CallTraceLatencyPanel({ trace }: { trace: TracePayload }) {
  const turns = useMemo(() => traceTurnLatencies(trace.turns || []), [trace.turns]);
  const maxMs = useMemo(
    () => Math.max(1, ...turns.flatMap((t) => [t.sttMs, t.llmMs, t.ttsMs, t.e2eMs])),
    [turns]
  );

  return (
    <SkeuoPanel
      title="Latency waterfall"
      description="Per-turn STT · LLM TTFT · TTS first audio · E2E"
      padding="md"
    >
      {turns.length === 0 ? (
        <p className="text-sm text-text-muted">No per-turn trace metrics yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {turns.map((t) => (
            <div key={t.turn} className="skeuo-inset rounded-skeuo-md p-4 space-y-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary">Turn {t.turn}</p>
              <Bar label="STT final" ms={t.sttMs} maxMs={maxMs} tone="bg-status-info/70" />
              <Bar label="LLM TTFT" ms={t.llmMs} maxMs={maxMs} tone="bg-accent-primary/70" />
              <Bar label="TTS first audio" ms={t.ttsMs} maxMs={maxMs} tone="bg-status-success/70" />
              <div className="border-t border-surface-border-subtle pt-2 font-mono text-xs text-text-muted">
                E2E <span className="text-text">{t.e2eMs}ms</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </SkeuoPanel>
  );
}

export function CallTracePanel({ trace }: { trace: TracePayload }) {
  const turns = trace.turns || [];

  return (
    <SkeuoPanel title="Trace" description="OpenInference-aligned turn spans from trace.json" padding="md">
      {turns.length === 0 ? (
        <p className="text-sm text-text-muted">Trace file empty or not yet written.</p>
      ) : (
        <ul className="max-h-64 space-y-2 overflow-y-auto font-mono text-[11px]">
          {turns.map((t: TraceTurn) => (
            <li key={t.turn} className="rounded-skeuo-sm skeuo-inset px-3 py-2 text-text-muted">
              <span className="text-accent-primary">turn {t.turn}</span>
              {" · "}
              stt {t.stt_final_ms ?? "—"}ms
              {" · "}
              llm {t.llm_ttft_ms ?? "—"}ms
              {" · "}
              tts {t.tts_first_audio_ms ?? "—"}ms
              {" · "}
              mem {t.memory_ops_applied ?? 0} ops
              {t.pipeline === "realtime_voice" && (
                <>
                  {" · "}
                  audio {(t.input_audio_tokens ?? 0) + (t.output_audio_tokens ?? 0)} tok
                  {t.cost_inr != null && ` · ₹${Number(t.cost_inr).toFixed(2)}`}
                </>
              )}
              {(t.errors || []).length > 0 && (
                <span className="text-status-error"> · errors {(t.errors || []).length}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {(trace.combination_id || trace.compiled_brain_version) && (
        <p className="mt-3 font-mono text-[10px] text-text-subtle break-all">
          {trace.combination_id && `combo ${trace.combination_id}`}
          {trace.compiled_brain_version && ` · brain ${trace.compiled_brain_version}`}
        </p>
      )}
    </SkeuoPanel>
  );
}
