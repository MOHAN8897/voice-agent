import { EnvironmentPanel } from "@/components/dev/EnvironmentPanel";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevEnvironmentPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Configuration"
        title="Environment & API keys"
        description="Platform mode, provider toggles, and masked secrets. Updates reload the provider registry without editing .env manually."
      />
      <EnvironmentPanel />
    </div>
  );
}
