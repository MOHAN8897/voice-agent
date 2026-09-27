"use client";

import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { CallMeta } from "@/lib/call-detail-types";
import { resolveTranscriptSource } from "@/lib/transcript-source";

export function CallTranscriptSourceBadge({ meta }: { meta?: CallMeta | null }) {
  const info = resolveTranscriptSource(meta);
  if (!info) return null;
  return (
    <div className="flex flex-col gap-1" data-testid="transcript-source-badge">
      <SkeuoBadge tone={info.isPostCallGemini ? "accent" : "muted"}>{info.badge}</SkeuoBadge>
      {info.detail ? <p className="text-xs leading-relaxed text-text-muted">{info.detail}</p> : null}
    </div>
  );
}
