"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import type { MemoryEvent, MemorySnapshot } from "@/lib/call-detail-types";

function TreeSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-3">
      <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary">{title}</p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function CallMemoryStatePanel({
  memory,
  events,
}: {
  memory: MemorySnapshot;
  events: MemoryEvent[];
}) {
  const facts = memory.facts || {};
  const prefs = memory.preferences || {};

  return (
    <SkeuoPanel
      title="Memory"
      description="Structured machine state — facts, preferences, context, summary"
      padding="md"
    >
      <div className="space-y-3">
        <TreeSection title="Facts">
          {Object.keys(facts).length === 0 ? (
            <p className="text-xs text-text-muted">No facts captured.</p>
          ) : (
            <ul className="space-y-1 font-mono text-xs text-text">
              {Object.entries(facts).map(([k, v]) => (
                <li key={k} className="flex gap-2">
                  <span className="text-text-subtle">├── {k}</span>
                  <span className="text-text">{v}</span>
                </li>
              ))}
            </ul>
          )}
        </TreeSection>

        <TreeSection title="Preferences">
          {Object.keys(prefs).length === 0 ? (
            <p className="text-xs text-text-muted">No preferences recorded.</p>
          ) : (
            <ul className="space-y-1 font-mono text-xs text-text">
              {Object.entries(prefs).map(([k, v]) => (
                <li key={k} className="flex gap-2">
                  <span className="text-text-subtle">├── {k}</span>
                  <span className="text-text">{v}</span>
                </li>
              ))}
            </ul>
          )}
        </TreeSection>

        <TreeSection title="Important context">
          <p className="text-sm text-text-muted whitespace-pre-wrap">
            {memory.important_context?.trim() || "—"}
          </p>
        </TreeSection>

        <TreeSection title="Summary">
          <p className="text-sm text-text whitespace-pre-wrap">{memory.summary?.trim() || "—"}</p>
        </TreeSection>

        {events.length > 0 && (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Event log</p>
            <ul className="mt-2 max-h-32 overflow-y-auto space-y-1 font-mono text-[10px] text-text-muted">
              {events.map((ev, i) => (
                <li key={i}>
                  turn {ev.turn_seq ?? "—"} · {ev.source || "model"} · {(ev.operations || []).length} ops
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </SkeuoPanel>
  );
}
