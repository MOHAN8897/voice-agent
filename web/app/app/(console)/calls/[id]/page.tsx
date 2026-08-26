import Link from "next/link";
import { CallInvestigationConsole } from "@/components/calls/CallInvestigationConsole";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";

export default function CallDetailPage({ params }: { params: { id: string } }) {
  return (
    <ConsolePage className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageHeader
          eyebrow="Call investigation"
          title="Investigation workspace"
          description="Outcome, audio, transcript timeline, pipeline trace, memory state, and metadata — unified per-call debugging."
        />
        <Link href="/app/calls">
          <SkeuoButton variant="ghost" size="sm">← Back to archive</SkeuoButton>
        </Link>
      </div>

      <CallInvestigationConsole callId={params.id} />
    </ConsolePage>
  );
}
