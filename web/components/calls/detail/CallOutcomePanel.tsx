"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { OutcomePayload } from "@/lib/call-detail-types";

export function CallOutcomePanel({ outcome }: { outcome: OutcomePayload | null }) {
  return (
    <SkeuoPanel title="Outcome" description="Post-call LLM disposition and extracted fields" padding="md">
      {!outcome ? (
        <p className="text-sm text-text-muted">Outcome pending or not generated yet.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <SkeuoBadge tone="info">{outcome.disposition || "no_outcome"}</SkeuoBadge>
            {outcome.disposition_confidence != null && (
              <span className="font-mono text-[10px] text-text-subtle">
                confidence {(outcome.disposition_confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>

          {outcome.summary_te && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Summary · Telugu</p>
              <p className="mt-1 text-sm leading-relaxed text-text">{outcome.summary_te}</p>
            </div>
          )}
          {outcome.summary_en && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Summary · English</p>
              <p className="mt-1 text-sm leading-relaxed text-text-muted">{outcome.summary_en}</p>
            </div>
          )}

          {outcome.next_action && (
            <div className="skeuo-inset rounded-skeuo-sm p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary">Next action</p>
              <p className="mt-1 text-sm text-text">{outcome.next_action}</p>
            </div>
          )}

          {outcome.extracted_fields && Object.keys(outcome.extracted_fields).length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Extracted fields</p>
              <ul className="mt-2 space-y-1">
                {Object.entries(outcome.extracted_fields).map(([k, v]) => (
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
