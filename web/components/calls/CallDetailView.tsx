"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";

type TranscriptLine = { role?: string; text?: string };

export function CallDetailView({ callId }: { callId: string }) {
  const [meta, setMeta] = useState<Record<string, unknown>>({});
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [tab, setTab] = useState<"transcript" | "memory" | "outcome">("transcript");
  const [memory, setMemory] = useState<Record<string, unknown>>({});
  const [outcome, setOutcome] = useState<Record<string, unknown> | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [metaR, txR, memR, outR] = await Promise.all([
        fetch(`/api/call/${callId}`),
        fetch(`/api/call/${callId}/transcript`),
        fetch(`/api/call/${callId}/memory`),
        fetch(`/api/call/${callId}/outcome`),
      ]);
      if (cancelled) return;
      if (metaR.ok) setMeta(await metaR.json());
      if (txR.ok) {
        const tx = await txR.json();
        setLines(ensureArray<TranscriptLine>(tx.lines));
      }
      if (memR.ok) {
        const mem = await memR.json();
        setMemory((mem.memory as Record<string, unknown>) || {});
      }
      if (outR.ok) {
        const out = await outR.json();
        setOutcome((out.outcome as Record<string, unknown>) || null);
      }
      const audioProbe = await fetch(`/api/call/${callId}/audio/mix`, { method: "HEAD" });
      if (!cancelled && audioProbe.ok) setAudioUrl(`/api/call/${callId}/audio/mix`);
    })();
    return () => {
      cancelled = true;
    };
  }, [callId]);

  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-wider text-text-subtle">
        Status {String(meta.finalization_status ?? meta.status ?? "—")} · stack{" "}
        {String(meta.combination_id ?? "—")}
      </p>
      <div className="mt-4 flex gap-1 border-b border-surface-border-subtle pb-2">
        {(["transcript", "memory", "outcome"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={`rounded-lg px-3 py-1.5 text-sm capitalize ${
              tab === name ? "bg-accent-dim text-accent" : "text-text-muted hover:text-text"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "transcript" && (
        <div className="mt-4">
          <h2 className="text-lg font-medium">Transcript</h2>
          <ul className="mt-3 space-y-2">
            {lines.length === 0 ? (
              <li className="text-sm text-text-muted">No transcript lines yet.</li>
            ) : (
              lines.map((l, i) => (
                <li key={i} className="rounded-xl border border-surface-border-subtle bg-surface-card px-3 py-2 text-sm">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{l.role}</span>
                  <p className="mt-1 text-text">{l.text}</p>
                </li>
              ))
            )}
          </ul>
          {audioUrl ? (
            <div className="mt-4">
              <audio controls src={audioUrl} className="w-full" />
              <button
                type="button"
                onClick={() => {
                  const el = document.querySelector<HTMLAudioElement>(`audio[src="${audioUrl}"]`);
                  el?.play();
                }}
                className="mt-2 rounded-xl border border-surface-border px-3 py-1.5 text-sm text-text"
              >
                Play audio
              </button>
            </div>
          ) : (
            <button type="button" disabled className="mt-4 rounded-xl border border-surface-border px-3 py-1.5 text-sm opacity-50">
              Play audio
            </button>
          )}
        </div>
      )}

      {tab === "memory" && (
        <div className="mt-4">
          <h2 className="text-lg font-medium">Memory</h2>
          <pre className="mt-3 overflow-auto rounded-xl border border-surface-border-subtle bg-surface-raised p-3 font-mono text-xs text-text-muted">
            {JSON.stringify(memory, null, 2)}
          </pre>
        </div>
      )}

      {tab === "outcome" && (
        <div className="mt-4">
          <h2 className="text-lg font-medium">Outcome</h2>
          {outcome ? (
            <pre className="mt-3 overflow-auto rounded-xl border border-surface-border-subtle bg-surface-raised p-3 font-mono text-xs text-text-muted">
              {JSON.stringify(outcome, null, 2)}
            </pre>
          ) : (
            <p className="mt-2 text-sm text-text-muted">Outcome pending or not generated yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
