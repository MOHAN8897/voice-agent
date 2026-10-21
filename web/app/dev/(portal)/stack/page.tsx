import { StackTierWorkbench } from "@/components/dev/StackTierWorkbench";
import { PstnVoiceProfileWorkbench } from "@/components/dev/PstnVoiceProfileWorkbench";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevStackPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform voice configuration"
        title="Voice stacks & PSTN tiers"
        description="Configure composed PSTN profiles, review readiness, then manage the separate legacy stage assignments."
      />
      <div className="mt-6">
        <PstnVoiceProfileWorkbench />
      </div>
      <StackTierWorkbench />
    </div>
  );
}
