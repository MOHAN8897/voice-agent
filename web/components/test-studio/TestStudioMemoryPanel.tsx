"use client";

import { useEffect, useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";

type Tab = "projection" | "events" | "snapshot";

export function TestStudioMemoryPanel({
  callId,
  projectionJson,
}: {
  callId: string | null;
  projectionJson: string;
}) {
  const [tab, setTab] = useState<Tab>("projection");
  const [eventsJson, setEventsJson] = useState("");
  const [snapshotJson, setSnapshotJson] = useState("");

  useEffect(() => {
    if (!callId) {
      setEventsJson("");
      setSnapshotJson("");
      return;
    }
    fetch(`/api/call/${callId}/memory-events`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setEventsJson(JSON.stringify(j?.events || j || [], null, 2)))
      .catch(() => setEventsJson(""));
    fetch(`/api/call/${callId}/memory`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setSnapshotJson(JSON.stringify(j?.snapshot || j || {}, null, 2)))
      .catch(() => setSnapshotJson(""));
  }, [callId, projectionJson]);

  const body =
    tab === "projection" ? projectionJson : tab === "events" ? eventsJson : snapshotJson;

  return (
    <SkeuoPanel title="Working memory" description="Layer B snapshot · C projection · events per turn" padding="md">
      <div className="mb-2 flex gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1">
        {(
          [
            ["projection", "Projection (C)"],
            ["events", "Events"],
            ["snapshot", "Snapshot (B)"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              "flex-1 rounded-skeuo-sm px-2 py-1 text-[10px] font-medium",
              tab === id ? "bg-accent text-accent-fg" : "text-text-muted hover:bg-surface-raised"
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <pre className="max-h-44 overflow-auto font-mono text-[10px] text-text-muted skeuo-inset rounded-skeuo-sm p-3">
        {body || (callId ? "Loading…" : "Start a call to inspect dynamic memory.")}
      </pre>
    </SkeuoPanel>
  );
}
