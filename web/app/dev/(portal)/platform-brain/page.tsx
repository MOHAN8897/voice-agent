import { PlatformBrainEditor } from "@/components/dev/PlatformBrainEditor";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevPlatformBrainPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Protected"
        title="Platform Brain"
        description="Developer-owned identity, safety, language rules, and output contract. Customers cannot read this."
      />
      <PlatformBrainEditor />
    </div>
  );
}
