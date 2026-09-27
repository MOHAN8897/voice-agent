"use client";

import { useCallback, useEffect, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";

export type LivePromptPreview = {
  live_prompt?: string;
  compiled_brain?: string;
  token_estimate?: number;
  provider?: string;
  opening_line?: string;
  prewarm_greeting_line?: string;
  script_entities?: Record<string, string>;
  note?: string;
  call_id?: string;
  session_id?: string;
};

type Props = {
  sessionId: string;
  callId?: string | null;
  direction?: string;
  llmModel?: string;
  pipeline?: string;
  className?: string;
};

export function LivePromptPreviewPanel({
  sessionId,
  callId,
  direction = "outbound",
  llmModel,
  pipeline = "realtime_voice",
  className,
}: Props) {
  const [tab, setTab] = useState<"live" | "brain" | "prewarm">("live");
  const [data, setData] = useState<LivePromptPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (callId) {
        const r = await fetch(`/api/call/${encodeURIComponent(callId)}/prompt-preview`, {
          credentials: "include",
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.detail || j.message || `HTTP ${r.status}`);
        setData({
          live_prompt: j.live_prompt,
          compiled_brain: undefined,
          token_estimate: j.token_estimate,
          provider: j.provider,
          opening_line: j.opening_line,
          script_entities: j.script_entities,
          note: j.note,
          call_id: j.call_id,
        });
        return;
      }
      params.set("sessionId", sessionId);
      params.set("direction", direction);
      params.set("pipeline", pipeline);
      if (llmModel) params.set("llmModel", llmModel);
      const r = await fetch(`/api/instructions/live-prompt-preview?${params}`, {
        credentials: "include",
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || j.message || `HTTP ${r.status}`);
      setData(j as LivePromptPreview);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load prompt preview");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId, callId, direction, llmModel, pipeline]);

  useEffect(() => {
    void load();
  }, [load]);

  const body =
    tab === "live"
      ? data?.live_prompt
      : tab === "brain"
        ? data?.compiled_brain
        : [
            data?.prewarm_greeting_line
              ? `Prewarm deferred opening (PCM at connect):\n${data.prewarm_greeting_line}`
              : "",
            data?.opening_line ? `\nSystem opening_line field:\n${data.opening_line}` : "",
          ]
            .filter(Boolean)
            .join("\n\n") || "(No prewarm line — create script with @opening_line)";

  return (
    <div className={cn("rounded-skeuo-sm border border-surface-border-subtle p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-text">Live LLM system prompt</p>
          <p className="mt-0.5 text-[11px] text-text-muted">
            {callId
              ? "Locked prompt for this active call (connect-time)."
              : "Preview from saved session brain — matches PSTN when you dial from Test Studio."}
            {data?.provider ? ` · ${data.provider}` : ""}
            {data?.token_estimate != null ? ` · ~${data.token_estimate} tokens` : ""}
          </p>
        </div>
        <SkeuoButton type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void load()}>
          {loading ? "Loading…" : "Refresh"}
        </SkeuoButton>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {(
          [
            ["live", "Full live prompt"],
            ["brain", "Compiled brain only"],
            ["prewarm", "Prewarm opening"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={cn(
              "rounded-full border px-2.5 py-1 text-[11px]",
              tab === id
                ? "border-accent bg-accent/10 text-text"
                : "border-surface-border-subtle text-text-muted hover:bg-surface-raised"
            )}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {error ? <p role="alert" className="mt-2 text-xs text-danger">{error}</p> : null}
      {data?.note ? <p className="mt-2 text-[10px] text-text-subtle">{data.note}</p> : null}
      <pre
        className="mt-3 max-h-[420px] overflow-auto rounded-lg border border-surface-border-subtle bg-surface-raised/50 p-3 font-mono text-[10px] text-text-muted whitespace-pre-wrap"
      >
        {loading && !data ? "Loading…" : body || "—"}
      </pre>
    </div>
  );
}
