import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";
import { ConsolePage } from "@/components/console/ConsolePage";

export default function AgentTestStudioPage({ params }: { params: { agentId: string } }) {
  return (
    <ConsolePage>
      <AgentTestStudio key={params.agentId} agentId={params.agentId} portal="app" />
    </ConsolePage>
  );
}
