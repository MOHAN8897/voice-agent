"use client";

import { useEffect, useState } from "react";
import { BusinessBrainEditor, orderBrainSections } from "@/components/agents/BusinessBrainEditor";
import { BRAIN_SECTION_LABELS, BRAIN_SECTION_ORDER } from "@/lib/constants";

type Section = {
  section_id: string;
  type: string;
  title: string;
  raw_text: string;
  order: number;
  enabled: boolean;
};

function fallbackSections(): Section[] {
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
  const [sections, setSections] = useState<Section[]>(fallbackSections());

  useEffect(() => {
    fetch(`/api/agents/${agentId}/business-brain`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const loaded = data?.draft?.sections || [];
        if (loaded.length) setSections(orderBrainSections(loaded));
      });
  }, [agentId]);

  return <BusinessBrainEditor agentId={agentId} initialSections={sections} />;
}
