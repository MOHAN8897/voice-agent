import { apiGet } from "@/lib/api";
import { redirect } from "next/navigation";
import { PageHeader } from "@/components/console/PageHeader";
import { EmptyState } from "@/components/console/EmptyState";

export default async function TestStudioRedirectPage() {
  let agentId: string | null = null;
  try {
    const data = await apiGet<{ agents?: Array<{ agent_id: string }> }>("/api/agents");
    agentId = data.agents?.[0]?.agent_id ?? null;
  } catch {
    agentId = null;
  }

  if (agentId) {
    redirect(`/app/agents/${agentId}/test`);
  }

  return (
    <div>
      <PageHeader title="Test Studio" description="Live browser mic against a locked agent version." />
      <div className="mt-8">
        <EmptyState title="Create an agent first" body="Test Studio needs an agent with a Business Brain before a live session can start." actionHref="/app/agents" actionLabel="Go to Agents" />
      </div>
    </div>
  );
}
