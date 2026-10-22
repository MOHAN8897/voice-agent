import { Suspense } from "react";
import { TestStudioHome } from "@/components/test-studio/TestStudioHome";
import { TestStudioLegacyAgentRedirect } from "@/components/test-studio/TestStudioLegacyAgentRedirect";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevTestStudioPage() {
  return (
    <div>
      <Suspense fallback={null}>
        <TestStudioLegacyAgentRedirect portal="dev" />
      </Suspense>
      <PageHeader
        eyebrow="Workbench"
        title="Test Studio"
        description="Agent sidebar on the left — brief, stack, and PSTN settings stay per agent."
      />
      <Suspense fallback={<p className="text-sm text-text-muted">Loading Test Studio…</p>}>
        <TestStudioHome portal="dev" />
      </Suspense>
    </div>
  );
}
