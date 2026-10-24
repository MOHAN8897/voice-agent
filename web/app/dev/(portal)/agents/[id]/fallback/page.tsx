import { TechnicalFallbackPanel } from "@/components/dev/TechnicalFallbackPanel";

export default async function DevAgentFallbackPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TechnicalFallbackPanel agentId={id} />;
}
