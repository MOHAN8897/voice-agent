import { ProviderStatusGrid } from "@/components/dev/ProviderStatusGrid";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevProvidersPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Catalog"
        title="Provider status"
        description="Configured keys, adapter availability, and health — secrets never appear in the UI."
      />
      <ProviderStatusGrid />
    </div>
  );
}
