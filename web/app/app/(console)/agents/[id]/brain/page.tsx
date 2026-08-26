import { BusinessBrainEditor } from "@/components/agents/BusinessBrainEditor";
import { BRAIN_SECTION_LABELS, BRAIN_SECTION_ORDER } from "@/lib/constants";
import { orderBrainSections, type BrainSection } from "@/lib/brain-utils";
import { apiGet } from "@/lib/api";

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

export default async function AgentBrainPage({ params }: { params: { id: string } }) {
  let sections: BrainSection[] = fallbackSections();
  let published: Record<string, unknown> | null = null;
  let versionsCount = 0;
  let rawChecksum = "";

  try {
    const data = await apiGet<{
      draft?: { sections?: BrainSection[]; raw_checksum?: string };
      published?: Record<string, unknown> | null;
      versions_count?: number;
    }>(`/api/agents/${params.id}/business-brain`);
    const loaded = data.draft?.sections || [];
    if (loaded.length) sections = orderBrainSections(loaded);
    published = data.published ?? null;
    versionsCount = data.versions_count ?? 0;
    rawChecksum = data.draft?.raw_checksum || "";
  } catch {
    sections = fallbackSections();
  }

  return (
    <BusinessBrainEditor
      agentId={params.id}
      initialSections={sections}
      published={published as { version_id?: string; optimized_prompt?: string; optimizer_report?: { optimizer_model?: string } } | null}
      versionsCount={versionsCount}
      initialChecksum={rawChecksum}
    />
  );
}
