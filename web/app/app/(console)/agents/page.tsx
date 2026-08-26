import { apiGet } from "@/lib/api";
import Link from "next/link";
import { AgentsRack, type AgentRackItem } from "@/components/agents/AgentRackCard";
import { ConsolePage } from "@/components/console/ConsolePage";
import { EmptyState } from "@/components/console/EmptyState";
import { PageHeader } from "@/components/console/PageHeader";
import { SkeuoButton } from "@/components/ui/skeuo";

export default async function AgentsPage() {
  let agents: AgentRackItem[] = [];
  try {
    const data = await apiGet<{ agents?: AgentRackItem[] }>("/api/agents");
    agents = data.agents || [];
  } catch {
    agents = [];
  }

  return (
    <ConsolePage>
      <PageHeader
        eyebrow="Equipment rack"
        title="Agents"
        description="Each module is a deployable voice agent — brain, tier, channels, and promoted version."
        actions={
          <Link href="/app/test-studio">
            <SkeuoButton variant="metal" size="sm">Test Studio</SkeuoButton>
          </Link>
        }
      />

      {agents.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No agents yet"
            body="Seed the default agent from API startup, then open the workspace to edit the Business Brain."
          />
        </div>
      ) : (
        <AgentsRack agents={agents} portal="app" />
      )}
    </ConsolePage>
  );
}
