import { apiGet } from "@/lib/api";
import { Panel } from "@/components/console/Panel";
import { EmptyState } from "@/components/console/EmptyState";

export default async function AgentVersionsPage({ params }: { params: { id: string } }) {
  let versions: unknown[] = [];
  try {
    const data = await apiGet<{ versions?: unknown[] }>(`/api/agents/${params.id}/business-brain/versions`);
    versions = data.versions || [];
  } catch {
    versions = [];
  }

  return (
    <div>
      <p className="text-sm text-text-muted">Published business brain versions. Production calls lock the version at start.</p>
      {versions.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="No published versions" body="Save a draft and publish from the Business Brain tab." />
        </div>
      ) : (
        <Panel className="mt-6" title="History">
          <pre className="overflow-auto font-mono text-xs text-text-muted">{JSON.stringify(versions, null, 2)}</pre>
        </Panel>
      )}
    </div>
  );
}
