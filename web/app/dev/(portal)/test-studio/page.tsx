import { Suspense } from "react";
import { DevTestStudio } from "@/components/dev/DevTestStudio";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevTestStudioPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Workbench"
        title="Test Studio"
        description="Live voice lab — tier presets or per-stage STT / LLM / TTS overrides. Use Agents to edit business brain and deployment."
      />
      <Suspense fallback={<p className="text-sm text-text-muted">Loading Test Studio…</p>}>
        <DevTestStudio />
      </Suspense>
    </div>
  );
}
