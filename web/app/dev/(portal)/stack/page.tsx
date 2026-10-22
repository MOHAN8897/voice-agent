import { PstnVoiceProfileWorkbench } from "@/components/dev/PstnVoiceProfileWorkbench";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevStackPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform voice configuration"
        title="Voice stacks & PSTN tiers"
        description="Configure composed PSTN profiles, pipeline stage models, readiness evidence, retail rates, and platform activation."
      />
      <div className="mt-6">
        <PstnVoiceProfileWorkbench />
      </div>
    </div>
  );
}
