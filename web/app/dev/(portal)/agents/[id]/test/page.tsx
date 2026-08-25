import { DevAgentTestStudio } from "@/components/dev/DevAgentTestStudio";

export default function DevAgentTestPage({ params }: { params: { id: string } }) {
  return <DevAgentTestStudio agentId={params.id} />;
}
