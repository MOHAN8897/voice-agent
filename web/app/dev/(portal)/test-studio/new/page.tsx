import { PageHeader } from "@/components/console/PageHeader";
import { TestStudioCreateAgent } from "@/components/test-studio/TestStudioCreateAgent";

export default function DevTestStudioNewAgentPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Test Studio"
        title="New agent"
        description="Brief-first creation — language, direction, and role shape the compiled script."
      />
      <TestStudioCreateAgent portal="dev" />
    </div>
  );
}
