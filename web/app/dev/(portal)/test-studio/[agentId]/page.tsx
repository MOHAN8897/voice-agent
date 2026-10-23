import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";

export default async function DevAgentTestStudioPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <AgentTestStudio key={agentId} agentId={agentId} portal="dev" />;
}
