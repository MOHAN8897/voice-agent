import { BusinessBrainEditor, orderBrainSections } from "@/components/agents/BusinessBrainEditor";
import { BRAIN_SECTION_LABELS, BRAIN_SECTION_ORDER } from "@/lib/constants";
import { apiGet } from "@/lib/api";

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

export default async function AgentBrainPage({ params }: { params: { id: string } }) {
  let sections: Section[] = fallbackSections();
  try {
    const data = await apiGet<{ draft?: { sections?: Section[] } }>(
      `/api/agents/${params.id}/business-brain`
    );
    const loaded = data.draft?.sections || [];
    if (loaded.length) sections = orderBrainSections(loaded);
  } catch {
    sections = fallbackSections();
  }

  return <BusinessBrainEditor agentId={params.id} initialSections={sections} />;
}
