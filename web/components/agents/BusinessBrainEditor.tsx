"use client";

import { useCallback, useEffect, useState } from "react";
import { BRAIN_SECTION_LABELS, BRAIN_SECTION_ORDER } from "@/lib/constants";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type Section = {
  section_id: string;
  type: string;
  title: string;
  raw_text: string;
  order: number;
  enabled: boolean;
};

function labelFor(section: Section): string {
  return BRAIN_SECTION_LABELS[section.type] || section.title;
}

export function BusinessBrainEditor({
  agentId,
  initialSections,
}: {
  agentId: string;
  initialSections: Section[];
}) {
  const [sections, setSections] = useState<Section[]>(initialSections);
  const [status, setStatus] = useState("");

  useEffect(() => {
    refreshPortalSession("app");
  }, []);

  function updateText(sectionId: string, raw_text: string) {
    setSections((prev) => prev.map((s) => (s.section_id === sectionId ? { ...s, raw_text } : s)));
  }

  const save = useCallback(async () => {
    setStatus("Saving…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/draft`, {
      method: "PUT",
      body: JSON.stringify({ sections }),
    });
    setStatus(r.ok ? "Draft saved" : "Save failed");
  }, [agentId, sections]);

  const publish = useCallback(async () => {
    setStatus("Publishing…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/publish`, { method: "POST" });
    setStatus(r.ok ? "Published" : "Publish failed");
  }, [agentId]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Business Brain</h2>
          <p className="mt-1 text-sm text-text-muted">Raw sections compile into one versioned prompt. Optimizer never overwrites source.</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={save}
            className="rounded-xl border border-surface-border bg-surface-card px-4 py-2 text-sm text-text hover:border-accent/40"
          >
            Save draft
          </button>
          <button type="button" onClick={publish} className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white">
            Publish
          </button>
        </div>
      </div>
      {status && <p className="mt-3 text-sm text-text-muted">{status}</p>}
      <div className="mt-6 space-y-3">
        {sections.map((section) => (
          <details key={section.section_id} open className="rounded-2xl border border-surface-border-subtle bg-surface-card">
            <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-text">{labelFor(section)}</summary>
            <div className="border-t border-surface-border-subtle px-4 py-3">
              <textarea
                className="w-full rounded-xl border border-surface-border bg-surface px-3 py-2 font-mono text-sm text-text focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                rows={6}
                value={section.raw_text}
                onChange={(e) => updateText(section.section_id, e.target.value)}
                aria-label={labelFor(section)}
              />
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

export function orderBrainSections(sections: Section[]): Section[] {
  const ordered = BRAIN_SECTION_ORDER.map((type) => sections.find((s) => s.type === type)).filter(
    Boolean
  ) as Section[];
  const extras = sections.filter((s) => !BRAIN_SECTION_ORDER.includes(s.type as (typeof BRAIN_SECTION_ORDER)[number]));
  return [...ordered, ...extras];
}
