import { AgentSummaryPanel } from "@/components/agents/AgentSummaryPanel";

export default function DevAgentSummaryPage({ params }: { params: { id: string } }) {
  return <AgentSummaryPanel agentId={params.id} basePath={`/dev/agents/${params.id}`} />;
}
