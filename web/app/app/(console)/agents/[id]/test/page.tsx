import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";

export default function AgentTestPage({ params }: { params: { id: string } }) {
  return <AgentTestStudio agentId={params.id} portal="app" />;
}
