import { DevAgentsGrid } from "@/components/dev/DevAgentsGrid";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevAgentsPage() {
  return (
    <ConsolePage>
      <PageHeader
        eyebrow="Equipment rack"
        title="Agents"
        description="Mirror of business agent workspace — open any module to edit brains, voice tiers, channels, and versions."
      />
      <DevAgentsGrid />
    </ConsolePage>
  );
}
