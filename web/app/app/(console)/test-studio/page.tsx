import { Suspense } from "react";
import { TestStudioHome } from "@/components/test-studio/TestStudioHome";
import { TestStudioLegacyAgentRedirect } from "@/components/test-studio/TestStudioLegacyAgentRedirect";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";

export default function TestStudioPage() {
  return (
    <ConsolePage>
      <Suspense fallback={null}>
        <TestStudioLegacyAgentRedirect portal="app" />
      </Suspense>
      <PageHeader
        eyebrow="Voice lab"
        title="Test Studio"
        description="Agent sidebar on the left — each agent has its own isolated lab."
      />
      <TestStudioHome portal="app" />
    </ConsolePage>
  );
}
