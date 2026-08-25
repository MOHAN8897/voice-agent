"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

export function DevCompiledPreview() {
  const [agents, setAgents] = useState<{ agent_id: string; name: string }[]>([]);
  const [agentId, setAgentId] = useState("");
  const [preview, setPreview] = useState("");
  const [layers, setLayers] = useState<{ layer: string; version_id?: string; precedence: number; description: string }[]>([]);
  const [meta, setMeta] = useState<{ compiled_version?: string; checksum?: string; token_estimate?: number }>({});

  useEffect(() => {
    refreshPortalSession("dev").then(() =>
      fetch("/api/agents", { credentials: "include" })
        .then((r) => r.json())
        .then((j) => {
          const list = ensureArray<{ agent_id: string; name: string }>(j.agents);
          setAgents(list);
          if (list[0]) setAgentId(list[0].agent_id);
        })
    );
  }, []);

  useEffect(() => {
    if (!agentId) return;
    portalFetch("dev", `/api/dev/compiled-preview?agent_id=${encodeURIComponent(agentId)}&redacted=true`)
      .then(async (r) => {
        if (!r.ok) return;
        const j = await r.json();
        setPreview(j.preview || "");
        setLayers(ensureArray(j.layers));
        setMeta({
          compiled_version: j.compiled_version,
          checksum: j.checksum,
          token_estimate: j.token_estimate,
        });
      });
  }, [agentId]);

  return (
    <div className="space-y-6">
      <DevCard title="Compiled brain preview" description="Platform + business + static layers with precedence">
        <label className="block text-sm">
          <span className="text-text-muted">Agent</span>
          <select
            className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
            ))}
          </select>
        </label>
        <dl className="mt-4 grid gap-2 text-xs text-text-muted sm:grid-cols-3">
          <div>
            <dt>Version</dt>
            <dd className="font-mono text-text">{meta.compiled_version || "—"}</dd>
          </div>
          <div>
            <dt>Checksum</dt>
            <dd className="font-mono text-text truncate">{meta.checksum || "—"}</dd>
          </div>
          <div>
            <dt>Est. tokens</dt>
            <dd className="font-mono text-text">{meta.token_estimate ?? "—"}</dd>
          </div>
        </dl>
        <ol className="mt-4 space-y-2 text-sm">
          {layers.map((l) => (
            <li key={l.layer} className="rounded-lg border border-surface-border-subtle px-3 py-2">
              <span className="font-mono text-accent">{l.precedence}</span>
              <span className="ml-2 font-medium text-text">{l.layer}</span>
              <span className="ml-2 text-xs text-text-subtle">{l.version_id}</span>
              <p className="mt-1 text-xs text-text-muted">{l.description}</p>
            </li>
          ))}
        </ol>
        <pre className="mt-4 max-h-96 overflow-auto rounded-xl bg-surface-raised p-4 font-mono text-xs text-text-muted whitespace-pre-wrap">
          {preview || "Select an agent to load compiled preview."}
        </pre>
      </DevCard>
    </div>
  );
}
