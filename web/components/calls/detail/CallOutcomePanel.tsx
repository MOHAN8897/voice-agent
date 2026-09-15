"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { OutcomePayload } from "@/lib/call-detail-types";

export function CallOutcomePanel({ outcome }: { outcome: OutcomePayload | null }) {
  const facts = outcome?.facts || outcome?.extracted_fields || {};
  return (
    <SkeuoPanel title="Call summary" description="Post-call summary, deterministic status, and captured facts" padding="md">
      {!outcome ? (
        <p className="text-sm text-text-muted">Outcome pending or not generated yet.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <SkeuoBadge tone="info">{outcome.disposition || "no_outcome"}</SkeuoBadge>
            <SkeuoBadge tone={outcome.generation_ok === false ? "warning" : "success"}>
              {outcome.generation_ok === false ? "Fallback summary" : "Summary complete"}
            </SkeuoBadge>
            {outcome.disposition_confidence != null && (
              <span className="font-mono text-[10px] text-text-subtle">
                confidence {(outcome.disposition_confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {outcome.status_tags && outcome.status_tags.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Status tags</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {outcome.status_tags.map((tag) => (
                  <SkeuoBadge key={tag} tone="accent">{tag.replaceAll(":", " · ")}</SkeuoBadge>
                ))}
              </div>
            </div>
          )}

          {outcome.summary_en && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Summary</p>
              <p className="mt-1 text-sm leading-relaxed text-text">{outcome.summary_en}</p>
            </div>
          )}

          {outcome.next_action && (
            <div className="skeuo-inset rounded-skeuo-sm p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary">Next action</p>
              <p className="mt-1 text-sm text-text">{outcome.next_action}</p>
            </div>
          )}

          {Object.keys(facts).length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Captured facts</p>
              <ul className="mt-2 space-y-1">
                {Object.entries(facts).map(([k, v]) => (
                  <li key={k} className="flex justify-between gap-2 text-sm">
                    <span className="text-text-muted">{k}</span>
                    <span className="text-text">{v}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {outcome.objections && outcome.objections.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Objections</p>
              <ul className="mt-1 list-disc pl-4 text-sm text-text-muted">
                {outcome.objections.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </div>
          )}

          {outcome.notes && (
            <p className="text-xs text-text-subtle">{outcome.notes}</p>
          )}
        </div>
      )}
    </SkeuoPanel>
  );
}
