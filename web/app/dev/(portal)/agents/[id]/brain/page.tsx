import { DevAgentBrainClient } from "@/components/dev/DevAgentBrainClient";

export default async function DevAgentBrainPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DevAgentBrainClient agentId={id} />;
}
