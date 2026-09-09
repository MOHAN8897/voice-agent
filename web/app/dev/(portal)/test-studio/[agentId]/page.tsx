import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";

export default function DevAgentTestStudioPage({ params }: { params: { agentId: string } }) {
  return <AgentTestStudio key={params.agentId} agentId={params.agentId} portal="dev" />;
}
