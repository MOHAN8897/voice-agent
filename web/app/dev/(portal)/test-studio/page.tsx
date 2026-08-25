import { DevTestStudio } from "@/components/dev/DevTestStudio";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevTestStudioPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Workbench"
        title="Test Studio"
        description="Live browser voice test with STT, brain stream, TTS, barge-in, and transcript — same stack as production calls."
      />
      <DevTestStudio />
    </div>
  );
}
