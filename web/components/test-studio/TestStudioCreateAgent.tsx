"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { COMPILE_LANGUAGE_OPTIONS } from "@/lib/compile-languages";
import {
  testStudioAgentPath,
  testStudioHomePath,
} from "@/components/test-studio/TestStudioAgentSidebar";
import { bootstrapTestStudioAgent } from "@/lib/bootstrap-test-studio-agent";
import { testStudioSessionId } from "@/lib/test-studio-stack";
import { cn } from "@/lib/cn";

const ROLES: { id: string; label: string }[] = [
  { id: "sales", label: "Sales / outbound pitch" },
  { id: "lead_qualification", label: "Lead qualification" },
  { id: "support", label: "Customer support" },
  { id: "appointment", label: "Appointments / scheduling" },
  { id: "recruitment", label: "Recruitment" },
  { id: "education", label: "Education / coaching" },
  { id: "information", label: "Information / FAQ" },
  { id: "follow_up", label: "Follow-up" },
  { id: "other", label: "General" },
];

const inputCls =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm";

function labNameFromCompileResponse(j: Record<string, unknown>): string {
  const opt = j.optimizerReport as Record<string, unknown> | undefined;
  const ent = (j.scriptEntities || opt?.script_entities) as Record<string, string> | undefined;
  const agent = String(ent?.agent_name || opt?.agent_name || "").trim();
  const company = String(ent?.company_name || opt?.company_name || "").trim();
  if (agent && company) return `${agent} · ${company}`.slice(0, 255);
  if (agent) return agent.slice(0, 255);
  if (company) return company.slice(0, 255);
  return "Agent lab";
}

export function TestStudioCreateAgent({ portal }: { portal: "app" | "dev" }) {
  const router = useRouter();
  const [language, setLanguage] = useState<string>("te-IN");
  const [direction, setDirection] = useState<"outbound" | "inbound">("outbound");
  const [role, setRole] = useState("sales");
  const [brief, setBrief] = useState("");
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState("");

  async function runCreate() {
    const body = brief.trim();
    if (body.length < 8) {
      setError("Describe the business and agent in at least 8 characters.");
      return;
    }
    setBuilding(true);
    setError("");
    try {
      const r = await fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name: "Agent lab", languages: [language] }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail?.error?.message || `Create failed (${r.status})`);
      }
      const j = await r.json();
      const agentId = String(j.agent?.agent_id || "");
      if (!agentId) throw new Error("No agent id returned");

      await bootstrapTestStudioAgent(agentId, language);
      const sessionId = testStudioSessionId(agentId);
      const compileR = await fetch("/api/instructions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          sessionId,
          agentBrief: body,
          compileFromBrief: true,
          language_code: language,
          callDirection: direction,
          agentRole: role,
          brainPromptBudgetTokens: 6000,
        }),
      });
      const compileJ = await compileR.json().catch(() => ({}));
      if (!compileR.ok) {
        throw new Error(compileJ?.detail?.error?.message || `Script compile failed (${compileR.status})`);
      }

      const labName = labNameFromCompileResponse(compileJ as Record<string, unknown>);
      await fetch(`/api/agents/${agentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name: labName }),
      });

      router.push(testStudioAgentPath(agentId, portal));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create agent");
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl" data-testid="test-studio-create-agent">
      <SkeuoPanel
        title="Create agent from brief"
        description="Only the brief is required. Agent name, company, entity tags, and opening line are extracted from your text (or assigned by the compiler)."
        padding="md"
      >
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-text-muted">Spoken language</span>
              <select
                className={cn(inputCls, "mt-2")}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={building}
              >
                {(["India", "English (global)"] as const).map((group) => (
                  <optgroup key={group} label={group}>
                    {COMPILE_LANGUAGE_OPTIONS.filter((l) => l.group === group).map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.label}
                        {l.native ? ` (${l.native})` : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Call direction</span>
              <select
                className={cn(inputCls, "mt-2")}
                value={direction}
                onChange={(e) => setDirection(e.target.value as "outbound" | "inbound")}
                disabled={building}
              >
                <option value="outbound">Outbound — we place the call</option>
                <option value="inbound">Inbound — caller reaches us</option>
              </select>
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="text-text-muted">Role on the call</span>
              <select
                className={cn(inputCls, "mt-2")}
                value={role}
                onChange={(e) => setRole(e.target.value)}
                disabled={building}
              >
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </select>
            </label>
          </div>

          <label className="block text-sm">
            <span className="text-text-muted">Agent brief</span>
            <p className="mt-0.5 text-[11px] text-text-subtle">
              Include agent name and company here if you have them — no separate name field. Opening lines use natural
              phrasing for the language you pick (e.g. “Do you have a moment?”, “Meeku oka moment unda?”).
            </p>
            <textarea
              className={cn(inputCls, "mt-2 min-h-[200px] resize-y")}
              placeholder="Example: Agent name is Murthi. Business is Raghava Sales Private Limited — automobile spare parts in Hyderabad, Boduppal, with 20% discount…"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              disabled={building}
            />
          </label>

          {error ? (
            <p className="rounded-skeuo-sm border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <SkeuoButton
              variant="primary"
              disabled={building || brief.trim().length < 8}
              onClick={() => void runCreate()}
            >
              {building ? "Extracting & compiling…" : "Create agent & compile script"}
            </SkeuoButton>
            <SkeuoButton
              variant="secondary"
              disabled={building}
              onClick={() => router.push(testStudioHomePath(portal))}
            >
              Cancel
            </SkeuoButton>
          </div>
        </div>
      </SkeuoPanel>
    </div>
  );
}
