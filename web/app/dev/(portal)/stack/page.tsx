import { StackTierWorkbench } from "@/components/dev/StackTierWorkbench";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevStackPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Resolution"
        title="Stack & tiers"
        description="Assign STT, LLM, and TTS per LOW / MEDIUM / PREMIUM. Test combinations before promotion."
      />
      <StackTierWorkbench />
    </div>
  );
}
