import { DevAgentsGrid } from "@/components/dev/DevAgentsGrid";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevAgentsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Fleet"
        title="Agents"
        description="Mirror of business agent workspace — open any tab to edit brains, voice tiers, channels, and versions."
      />
      <DevAgentsGrid />
    </div>
  );
}
