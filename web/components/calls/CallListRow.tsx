"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/cn";
import {
  type CallListItem,
  callCustomerLabel,
  callSummaryLine,
  formatCallTime,
  formatDuration,
  pipelineLabel,
} from "@/lib/call-list-utils";
import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { formatInr } from "@/lib/usage-cost";

export function CallListRow({
  call,
  selected,
  onSelect,
}: {
  call: CallListItem;
  selected?: boolean;
  onSelect: () => void;
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  function togglePlay(e: React.MouseEvent) {
    e.stopPropagation();
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying) {
      el.pause();
      setIsPlaying(false);
    } else {
      el.play()
        .then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false));
    }
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full text-left rounded-skeuo-md border px-3 py-3 transition-all duration-150 relative",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/35",
        selected
          ? "border-accent-primary/35 bg-accent-primary/8 skeuo-panel shadow-sm"
          : "border-surface-border-subtle skeuo-inset hover:border-accent-primary/20"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
            {formatCallTime(call.started_at)}
          </p>
          <p className="mt-1 truncate text-sm font-medium text-text">{callCustomerLabel(call)}</p>
        </div>
        <StatusBadge tone={dispositionTone(call.disposition)}>
          {call.disposition || "pending"}
        </StatusBadge>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <SkeuoBadge tone="muted">{pipelineLabel(call.pipeline, call.channel)}</SkeuoBadge>
        <SkeuoBadge tone="info">{call.tier?.toUpperCase() || "—"}</SkeuoBadge>
        <span className="font-mono text-[10px] text-text-subtle">{formatDuration(call.duration_sec)}</span>
        {(call.cost_inr != null || call.usage?.cost_inr != null) && (
          <span className="font-mono text-[10px] text-text-subtle">
            {formatInr(Number(call.cost_inr ?? call.usage?.cost_inr ?? 0))}
          </span>
        )}

        {/* Direct Inline Recording Playout Button */}
        {call.has_recording && (
          <div className="inline-flex items-center" onClick={(e) => e.stopPropagation()}>
            <audio
              ref={audioRef}
              src={`/api/call/${encodeURIComponent(call.call_id)}/audio`}
              preload="none"
              onEnded={() => setIsPlaying(false)}
              onPause={() => setIsPlaying(false)}
              onPlay={() => setIsPlaying(true)}
            />
            <span
              role="button"
              tabIndex={0}
              onClick={togglePlay}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation();
                  togglePlay(e as unknown as React.MouseEvent);
                }
              }}
              className={cn(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold cursor-pointer transition-all",
                isPlaying
                  ? "bg-accent-primary text-white shadow-sm ring-2 ring-accent-primary/30"
                  : "bg-emerald-500/15 text-emerald-600 hover:bg-emerald-500/25 border border-emerald-500/30"
              )}
              title={isPlaying ? "Pause audio playback" : "Play recording directly"}
            >
              {isPlaying ? (
                <>
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-white animate-ping" />
                  <span>Pause</span>
                </>
              ) : (
                <>
                  <span>▶</span>
                  <span>Audio</span>
                </>
              )}
            </span>
          </div>
        )}
      </div>

      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-text-muted">{callSummaryLine(call)}</p>
    </button>
  );
}
