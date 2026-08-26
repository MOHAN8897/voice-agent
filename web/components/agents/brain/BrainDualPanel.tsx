"use client";

import { assembleRawPreview } from "@/lib/brain-utils";
import type { BrainSection } from "@/lib/brain-utils";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

export function BrainDualPanel({
  sections,
  optimizedText,
  publishedVersion,
  rawChecksum,
  optimizerModel,
}: {
  sections: BrainSection[];
  optimizedText: string | null;
  publishedVersion: string | null;
  rawChecksum?: string;
  optimizerModel?: string;
}) {
  const rawPreview = assembleRawPreview(sections);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SkeuoPanel
        title="User source"
        description="Raw sections — editable source of truth"
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

      <SkeuoPanel
        title="Optimized brain"
        description="Compiled internal prompt — review only"
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
    </div>
  );
}
