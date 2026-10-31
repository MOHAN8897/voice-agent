import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";
import { ConsolePage } from "@/components/console/ConsolePage";

export default async function AgentTestStudioPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return (
    <ConsolePage>
      <AgentTestStudio key={agentId} agentId={agentId} portal="app" />
    </ConsolePage>
  );
}
