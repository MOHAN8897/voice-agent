import { DevAgentBrainClient } from "@/components/dev/DevAgentBrainClient";

export default function DevAgentBrainPage({ params }: { params: { id: string } }) {
  return <DevAgentBrainClient agentId={params.id} />;
}
