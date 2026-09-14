"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ensureArray } from "@/lib/ensure-array";
import { compileLanguageLabel } from "@/components/test-studio/CompileLanguagePicker";
import type { AgentRackItem } from "@/components/agents/AgentRackCard";
import { SkeuoButton } from "@/components/ui/skeuo";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { cn } from "@/lib/cn";
import { formatAgentLanguage, notifyTestStudioAgentsChanged, TEST_STUDIO_AGENTS_CHANGED } from "@/lib/agent-language";
import { bootstrapTestStudioAgent } from "@/lib/bootstrap-test-studio-agent";
import { refreshPortalSession } from "@/lib/auth-client";

const LANGUAGES = ["te-IN", "en-IN", "en-US", "hi-IN"] as const;

export function testStudioAgentPath(agentId: string, portal: "app" | "dev") {
  return portal === "dev" ? `/dev/test-studio/${agentId}` : `/app/test-studio/${agentId}`;
}

export function testStudioHomePath(portal: "app" | "dev") {
  return portal === "dev" ? "/dev/test-studio" : "/app/test-studio";
}

export function parseTestStudioAgentId(pathname: string): string | null {
  const m = pathname.match(/\/test-studio\/([^/]+)/);
  return m?.[1] || null;
}

export function TestStudioAgentSidebar({ portal }: { portal: "app" | "dev" }) {
  const pathname = usePathname();
  const router = useRouter();
  const currentAgentId = parseTestStudioAgentId(pathname);
  const [agents, setAgents] = useState<AgentRackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newLanguage, setNewLanguage] = useState("te-IN");
  const [deletingId, setDeletingId] = useState("");

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (portal === "dev") await refreshPortalSession("dev");
      const r = await fetch("/api/agents", { credentials: "include" });
      if (!r.ok) throw new Error(`Could not load agents (${r.status})`);
      const j = await r.json();
      setAgents(ensureArray<AgentRackItem>(j.agents));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load agents");
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, [portal]);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    const onChanged = () => void loadAgents();
    window.addEventListener(TEST_STUDIO_AGENTS_CHANGED, onChanged);
    return () => window.removeEventListener(TEST_STUDIO_AGENTS_CHANGED, onChanged);
  }, [loadAgents]);

  async function createAgent() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setError("");
    try {
      const r = await fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, languages: [newLanguage] }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail?.error?.message || `Create failed (${r.status})`);
      }
      const j = await r.json();
      const agentId = String(j.agent?.agent_id || "");
      if (!agentId) throw new Error("Agent created but no id returned");
      await bootstrapTestStudioAgent(agentId, newLanguage);
      setNewName("");
      await loadAgents();
      router.push(testStudioAgentPath(agentId, portal));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create agent");
    } finally {
      setCreating(false);
    }
  }

  async function deleteAgent(agent: AgentRackItem) {
    const label = agent.name || agent.agent_id;
    if (!window.confirm(`Delete agent “${label}”? This removes its Test Studio lab (brief, stack, and voice).`)) {
      return;
    }
    setDeletingId(agent.agent_id);
    setError("");
    try {
      const r = await fetch(`/api/agents/${agent.agent_id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail?.error?.message || `Delete failed (${r.status})`);
      }
      notifyTestStudioAgentsChanged();
      await loadAgents();
      if (currentAgentId === agent.agent_id) {
        router.push(testStudioHomePath(portal));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete agent");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <aside
      className="flex h-full min-h-[28rem] w-full flex-col rounded-skeuo-lg border border-surface-border-subtle skeuo-panel lg:w-72 lg:shrink-0"
      data-testid="test-studio-agent-sidebar"
    >
      <div className="border-b border-surface-border-subtle px-4 py-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Test Studio</p>
        <h2 className="mt-1 text-base font-semibold text-text">Agent labs</h2>
        <p className="mt-1 text-xs text-text-muted">Each agent keeps its own brief, stack, and voice settings.</p>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <p className="px-2 py-3 text-sm text-text-muted">Loading agents…</p>
        ) : agents.length === 0 ? (
          <p className="px-2 py-3 text-sm text-text-muted">No agents yet. Create one below.</p>
        ) : (
          <ul className="space-y-2">
            {agents.map((agent) => {
              const active = currentAgentId === agent.agent_id;
              return (
                <li key={agent.agent_id} className="flex items-stretch gap-1">
                  <Link
                    href={testStudioAgentPath(agent.agent_id, portal)}
                    className={cn(
                      "min-w-0 flex-1 rounded-skeuo-sm border px-3 py-3 transition-colors",
                      active
                        ? "border-accent-primary/40 bg-accent-primary/10"
                        : "border-transparent hover:border-surface-border-subtle hover:bg-surface-panel-raised/50"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-medium text-text">{agent.name}</p>
                        <p className="mt-0.5 font-mono text-[10px] text-text-subtle truncate">{agent.agent_id}</p>
                      </div>
                      {active && <SkeuoBadge tone="success">Open</SkeuoBadge>}
                    </div>
                    <p className="mt-2 text-[11px] text-text-muted">
                      {formatAgentLanguage(agent)} · {agent.default_tier || "medium"}
                    </p>
                  </Link>
                  <button
                    type="button"
                    aria-label={`Delete ${agent.name}`}
                    title="Delete agent"
                    disabled={deletingId === agent.agent_id}
                    onClick={() => void deleteAgent(agent)}
                    className="shrink-0 self-start rounded-skeuo-sm px-2 py-2 text-xs text-text-subtle hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
                  >
                    {deletingId === agent.agent_id ? "…" : "✕"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-surface-border-subtle p-3 space-y-3">
        {error && (
          <p className="rounded-skeuo-sm border border-red-500/30 bg-red-500/10 px-2 py-1.5 text-xs text-red-200">{error}</p>
        )}
        <div className="space-y-2 rounded-skeuo-sm skeuo-inset p-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Create agent</p>
          <input
            className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-sm"
            placeholder="Agent name (e.g. Priya)"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={creating}
          />
          <select
            className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-sm"
            value={newLanguage}
            onChange={(e) => setNewLanguage(e.target.value)}
            disabled={creating}
            aria-label="Agent language"
          >
            {LANGUAGES.map((code) => (
              <option key={code} value={code}>{compileLanguageLabel(code)}</option>
            ))}
          </select>
          <SkeuoButton variant="primary" size="sm" className="w-full" disabled={creating || !newName.trim()} onClick={() => void createAgent()}>
            {creating ? "Creating…" : "Create agent"}
          </SkeuoButton>
        </div>
      </div>
    </aside>
  );
}
