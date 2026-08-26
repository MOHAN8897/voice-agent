"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ensureArray } from "@/lib/ensure-array";
import {
  BENCHMARK_METRICS,
  type BenchmarkCombination,
  type BenchmarkScenario,
  type BenchmarkSession,
} from "@/lib/benchmark-types";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoStatusLight } from "@/components/ui/skeuo/SkeuoStatusLight";
import { SkeuoInput } from "@/components/ui/skeuo/SkeuoInput";
import { cn } from "@/lib/cn";

const WORKFLOW = [
  "Create",
  "Environment",
  "Language",
  "Scenarios",
  "Combinations",
  "Estimate",
  "Run",
  "Compare",
  "Review",
  "Promote",
] as const;

type TierRow = { tier?: string; combination_id?: string; preview?: Record<string, unknown>; error?: string };

export function BenchmarkLaboratory({ portal = "app" }: { portal?: "app" | "dev" }) {
  const [enabled, setEnabled] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [scenarios, setScenarios] = useState<BenchmarkScenario[]>([]);
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [sessions, setSessions] = useState<BenchmarkSession[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("Telugu stack evaluation");
  const [environment, setEnvironment] = useState<"development" | "staging" | "production">("development");
  const [languages, setLanguages] = useState<string[]>(["te-IN"]);
  const [pickedScenarios, setPickedScenarios] = useState<string[]>([]);
  const [pickedTiers, setPickedTiers] = useState<string[]>(["low", "medium", "premium"]);
  const [loading, setLoading] = useState(true);

  const promotionHref = portal === "dev" ? "/dev/promotion" : "/app/settings";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [stR, scR, tR, sesR] = await Promise.all([
        fetch("/api/benchmarks/status", { credentials: "include" }),
        fetch("/api/test-scenarios", { credentials: "include" }),
        fetch("/api/tiers", { credentials: "include" }),
        fetch("/api/benchmark-sessions", { credentials: "include" }).catch(() => null),
      ]);
      if (stR.ok) {
        const j = await stR.json();
        setEnabled(Boolean(j.enabled));
        setStatusMsg(j.message || "");
      }
      if (scR.ok) {
        const j = await scR.json();
        setScenarios(ensureArray<BenchmarkScenario>(j.scenarios));
        if (pickedScenarios.length === 0 && j.scenarios?.[0]) {
          setPickedScenarios([j.scenarios[0].id]);
        }
      }
      if (tR.ok) {
        const j = await tR.json();
        setTiers(ensureArray<TierRow>(j.tiers));
      }
      if (sesR?.ok) {
        const j = await sesR.json();
        const list = ensureArray<BenchmarkSession>(j.sessions || j.runs);
        setSessions(list);
        if (list[0] && !selectedId) setSelectedId(list[0].session_id);
      }
    } finally {
      setLoading(false);
    }
  }, [pickedScenarios.length, selectedId]);

  useEffect(() => {
    load();
  }, [load]);

  const combinations: BenchmarkCombination[] = useMemo(
    () =>
      pickedTiers.map((tier) => {
        const row = tiers.find((t) => t.tier === tier);
        return {
          tier,
          combination_id: row?.combination_id,
          label: tier.toUpperCase(),
        };
      }),
    [pickedTiers, tiers]
  );

  const estimatedRuns = combinations.length * pickedScenarios.length;

  const selected = sessions.find((s) => s.session_id === selectedId) ?? null;

  async function createAndRun() {
    if (!enabled) return;
    const body = {
      name,
      environment,
      languages,
      scenario_ids: pickedScenarios,
      combinations,
    };
    const cr = await fetch("/api/benchmark-sessions", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!cr.ok) {
      setStatusMsg("Failed to create session — enable benchmarks in Dev Environment.");
      return;
    }
    const created = (await cr.json()) as BenchmarkSession;
    const sr = await fetch(`/api/benchmark-sessions/${created.session_id}/start`, {
      method: "POST",
      credentials: "include",
    });
    if (sr.ok) {
      const done = await sr.json();
      setSessions((prev) => [done, ...prev.filter((s) => s.session_id !== done.session_id)]);
      setSelectedId(done.session_id);
      setStatusMsg("Session recorded — awaiting benchmark runner for live metrics.");
    }
    await load();
  }

  function toggleScenario(id: string) {
    setPickedScenarios((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function toggleTier(tier: string) {
    setPickedTiers((prev) =>
      prev.includes(tier) ? prev.filter((x) => x !== tier) : [...prev, tier]
    );
  }

  function toggleLanguage(lang: string) {
    setLanguages((prev) =>
      prev.includes(lang) ? prev.filter((x) => x !== lang) : [...prev, lang]
    );
  }

  return (
    <ConsolePage className="space-y-6">
      <PageHeader
        eyebrow="Voice laboratory"
        title="Benchmarks"
        description="Reproducible combination evaluation — per-metric winners, not one mysterious score."
        actions={
          <Link href={promotionHref}>
            <SkeuoButton variant="secondary" size="sm">Promotion workflow</SkeuoButton>
          </Link>
        }
      />

      <SkeuoPanel title="Benchmark workflow" description="PRD §12 — create through promote" padding="md">
        <ol className="flex flex-wrap gap-2">
          {WORKFLOW.map((step, i) => (
            <li
              key={step}
              className="rounded-skeuo-sm border border-surface-border-subtle px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-text-subtle"
            >
              {String(i + 1).padStart(2, "0")} {step}
            </li>
          ))}
        </ol>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <SkeuoStatusLight status={enabled ? "ok" : "warn"} label={enabled ? "Enabled" : "Disabled"} />
          <span className="text-sm text-text-muted">{statusMsg}</span>
        </div>
      </SkeuoPanel>

      {!enabled && (
        <SkeuoPanel title="Benchmarks gated" padding="md">
          <p className="text-sm text-text-muted">
            Auto-runs stay inert until <span className="font-mono">ENABLE_BENCHMARKS=true</span> in Dev Environment.
            Scenario library and tier combinations below are available for planning.
          </p>
          {portal === "dev" && (
            <Link href="/dev/environment" className="mt-4 inline-block">
              <SkeuoButton variant="primary" size="sm">Open Environment</SkeuoButton>
            </Link>
          )}
        </SkeuoPanel>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <SkeuoPanel title="Create session" description="Environment · language · scenarios · combinations" padding="md">
          <div className="space-y-4">
            <label className="block text-sm">
              <span className="text-text-muted">Session name</span>
              <SkeuoInput className="mt-0" value={name} onChange={(e) => setName(e.target.value)} />
            </label>

            <div>
              <p className="text-sm text-text-muted">Environment</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(["development", "staging", "production"] as const).map((env) => (
                  <SkeuoButton
                    key={env}
                    size="sm"
                    variant={environment === env ? "primary" : "secondary"}
                    onClick={() => setEnvironment(env)}
                  >
                    {env}
                  </SkeuoButton>
                ))}
              </div>
            </div>

            <div>
              <p className="text-sm text-text-muted">Languages</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {["te-IN", "en-IN", "hi-IN"].map((lang) => (
                  <SkeuoButton
                    key={lang}
                    size="sm"
                    variant={languages.includes(lang) ? "primary" : "secondary"}
                    onClick={() => toggleLanguage(lang)}
                  >
                    {lang}
                  </SkeuoButton>
                ))}
              </div>
            </div>

            <div>
              <p className="text-sm text-text-muted">Scenarios</p>
              <ul className="mt-2 space-y-2">
                {scenarios.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => toggleScenario(s.id)}
                      className={cn(
                        "w-full rounded-skeuo-sm border px-3 py-2 text-left text-sm transition-all",
                        pickedScenarios.includes(s.id)
                          ? "border-accent-primary/35 bg-accent-primary/8"
                          : "border-surface-border-subtle skeuo-inset"
                      )}
                    >
                      <span className="font-medium text-text">{s.name}</span>
                      <span className="mt-1 block text-xs text-text-muted">{s.description}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="text-sm text-text-muted">Compatible combinations (tiers)</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {["low", "medium", "premium"].map((tier) => (
                  <SkeuoButton
                    key={tier}
                    size="sm"
                    variant={pickedTiers.includes(tier) ? "primary" : "secondary"}
                    onClick={() => toggleTier(tier)}
                  >
                    {tier}
                  </SkeuoButton>
                ))}
              </div>
              <ul className="mt-3 space-y-1 font-mono text-[10px] text-text-subtle">
                {combinations.map((c) => (
                  <li key={c.tier}>{c.tier}: {c.combination_id || "—"}</li>
                ))}
              </ul>
            </div>

            <div className="skeuo-inset rounded-skeuo-md p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Estimated runs</p>
              <p className="mt-1 font-mono text-lg text-text">{estimatedRuns}</p>
              <p className="mt-1 text-xs text-text-muted">
                {combinations.length} combinations × {pickedScenarios.length} scenarios
              </p>
            </div>

            <SkeuoButton variant="primary" disabled={!enabled || estimatedRuns === 0} onClick={createAndRun}>
              Create & record session
            </SkeuoButton>
          </div>
        </SkeuoPanel>

        <SkeuoPanel title="Sessions & compare" description="Per-metric winners when runner populates scores" padding="md">
          {loading ? (
            <p className="text-sm text-text-muted">Loading…</p>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-text-muted">No sessions yet. Create one when benchmarks are enabled.</p>
          ) : (
            <div className="space-y-4">
              <select
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm"
                value={selectedId || ""}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                {sessions.map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {s.name} · {s.status}
                  </option>
                ))}
              </select>

              {selected && (
                <>
                  <p className="font-mono text-[10px] text-text-subtle break-all">{selected.session_id}</p>
                  {selected.runner_note && (
                    <p className="text-xs text-status-warning">{selected.runner_note}</p>
                  )}

                  <div className="space-y-3">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Winners per metric</p>
                    {BENCHMARK_METRICS.map((m) => (
                      <div key={m.key} className="skeuo-inset rounded-skeuo-sm px-3 py-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-text-muted">{m.label}</span>
                          <span className="font-mono text-text">—</span>
                        </div>
                        <p className="mt-1 text-[10px] text-text-subtle">Awaiting runner-populated {m.key}</p>
                      </div>
                    ))}
                  </div>

                  <div className="max-h-48 overflow-y-auto">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Result matrix</p>
                    <ul className="mt-2 space-y-1 font-mono text-[10px] text-text-muted">
                      {(selected.results || []).map((r, i) => (
                        <li key={i}>
                          {r.combination_id} · {r.scenario_id} · {r.status || "pending"}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </div>
          )}
        </SkeuoPanel>
      </div>
    </ConsolePage>
  );
}
