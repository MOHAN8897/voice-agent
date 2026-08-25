"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/console/Panel";
import { EmptyState } from "@/components/console/EmptyState";

export default function DevAgentVersionsPage({ params }: { params: { id: string } }) {
  const [versions, setVersions] = useState<unknown[]>([]);

  useEffect(() => {
    fetch(`/api/agents/${params.id}/business-brain/versions`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { versions: [] }))
      .then((j) => setVersions(j.versions || []));
  }, [params.id]);

  return (
    <div>
      <p className="text-sm text-text-muted">Published business brain versions for this agent.</p>
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
