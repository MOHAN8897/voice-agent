import { AgentSummaryPanel } from "@/components/agents/AgentSummaryPanel";

export default async function DevAgentSummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AgentSummaryPanel agentId={id} basePath={`/dev/agents/${id}`} />;
}
