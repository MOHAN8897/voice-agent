"use client";

import { useEffect, useState } from "react";
import { BusinessBrainEditor } from "@/components/agents/BusinessBrainEditor";
import { BRAIN_SECTION_LABELS, BRAIN_SECTION_ORDER } from "@/lib/constants";
import { orderBrainSections, type BrainSection } from "@/lib/brain-utils";

function fallbackSections(): BrainSection[] {
  return BRAIN_SECTION_ORDER.map((type, i) => ({
    section_id: type,
    type,
    title: BRAIN_SECTION_LABELS[type],
    raw_text: "",
    order: (i + 1) * 10,
    enabled: true,
  }));
}

export function DevAgentBrainClient({ agentId }: { agentId: string }) {
  const [sections, setSections] = useState<BrainSection[]>(fallbackSections());
  const [published, setPublished] = useState<Record<string, unknown> | null>(null);
  const [versionsCount, setVersionsCount] = useState(0);
  const [checksum, setChecksum] = useState("");

  useEffect(() => {
    fetch(`/api/agents/${agentId}/business-brain`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const loaded = data?.draft?.sections || [];
        if (loaded.length) setSections(orderBrainSections(loaded));
        setPublished(data?.published ?? null);
        setVersionsCount(data?.versions_count ?? 0);
        setChecksum(data?.draft?.raw_checksum || "");
      });
  }, [agentId]);

  return (
    <BusinessBrainEditor
      agentId={agentId}
      initialSections={sections}
      published={published as { version_id?: string; optimized_prompt?: string; optimizer_report?: { optimizer_model?: string } } | null}
      versionsCount={versionsCount}
      initialChecksum={checksum}
    />
  );
}
