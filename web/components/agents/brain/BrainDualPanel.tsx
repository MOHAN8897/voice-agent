"use client";

import { assembleRawPreview } from "@/lib/brain-utils";
import type { BrainSection } from "@/lib/brain-utils";
import { cn } from "@/lib/cn";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

export function BrainDualPanel({
  sections,
  optimizedText,
  publishedVersion,
  rawChecksum,
  optimizerModel,
  showCompiledPreview = false,
}: {
  sections: BrainSection[];
  optimizedText: string | null;
  publishedVersion: string | null;
  rawChecksum?: string;
  optimizerModel?: string;
  showCompiledPreview?: boolean;
}) {
  const rawPreview = assembleRawPreview(sections);

  return (
    <div className={cn("grid gap-4", showCompiledPreview ? "lg:grid-cols-2" : "")}>
      <SkeuoPanel
        title="Your instructions"
        description="Exactly what you entered — source of truth"
        material="panel"
        padding="md"
        className="skeuo-brain-raw"
      >
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-text-secondary">
          {rawPreview || "No enabled sections."}
        </pre>
        {rawChecksum && (
          <p className="mt-3 font-mono text-[10px] text-text-subtle truncate">checksum {rawChecksum.slice(0, 16)}…</p>
        )}
      </SkeuoPanel>

      {showCompiledPreview && (
      <SkeuoPanel
        title="Compiled cache prompt"
        description="Internal LLM-compressed prompt — dev review only"
        material="inset"
        padding="md"
        className="skeuo-brain-optimized"
        headerAction={
          publishedVersion ? (
            <SkeuoBadge tone="warning" className="skeuo-brain-locked">
              LOCKED v{publishedVersion}
            </SkeuoBadge>
          ) : (
            <SkeuoBadge tone="muted">Not published</SkeuoBadge>
          )
        }
      >
        {optimizedText ? (
          <>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-text-muted">
              {optimizedText}
            </pre>
            {optimizerModel && (
              <p className="mt-3 font-mono text-[10px] text-text-subtle">Optimizer: {optimizerModel}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-text-muted">
            Run <span className="font-mono text-accent-primary">Optimize</span> to preview the internal compiled
            prompt. Publish locks a version for deployment.
          </p>
        )}
      </SkeuoPanel>
      )}
    </div>
  );
}
