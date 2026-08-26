"use client";

import { useCallback, useMemo, useState } from "react";
import { VoiceRackModule } from "@/components/voice/VoiceRackModule";
import { VoiceTierSelector } from "@/components/voice/VoiceTierSelector";
import { PageHeader } from "@/components/console/PageHeader";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { portalFetch } from "@/lib/auth-client";
import { TIER_META, type TierName } from "@/lib/voice-tier-meta";

type ResolvedPreview = {
  stt?: { provider?: string; model?: string };
  llm?: { provider?: string; model?: string };
  tts?: { provider?: string; model?: string };
  language?: string;
  combination_id?: string;
};

type TierRow = {
  tier: string;
  combination_id?: string;
  preview?: ResolvedPreview;
  error?: string;
};

type ProviderStatus = {
  id: string;
  healthy?: boolean;
  configured?: boolean;
};

function normalizeTier(t: string): TierName {
  const v = t.toLowerCase();
  if (v === "low" || v === "medium" || v === "premium") return v;
  return "medium";
}

function providerHealth(
  providers: ProviderStatus[],
  providerId?: string
): { healthy?: boolean; configured?: boolean } {
  if (!providerId) return {};
  const row = providers.find((p) => p.id === providerId);
  return { healthy: row?.healthy, configured: row?.configured };
}

export function AgentVoiceModelsPanel({
  agentId,
  initialTier,
  tiers,
  providers,
  configMode,
  readOnly = false,
  portal = "app",
}: {
  agentId: string;
  initialTier: string;
  tiers: TierRow[];
  providers: ProviderStatus[];
  configMode?: string;
  readOnly?: boolean;
  portal?: "app" | "dev";
}) {
  const [selectedTier, setSelectedTier] = useState<TierName>(normalizeTier(initialTier));
  const [agentTier, setAgentTier] = useState<TierName>(normalizeTier(initialTier));
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const tierRow = useMemo(
    () => tiers.find((t) => t.tier === selectedTier),
    [tiers, selectedTier]
  );
  const resolved = tierRow?.preview;

  const saveDefaultTier = useCallback(async () => {
    if (readOnly || portal !== "app") return;
    setBusy(true);
    setStatus("Saving default tier…");
    const r = await portalFetch("app", `/api/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify({ defaultTier: agentTier }),
    });
    setStatus(r.ok ? `Default tier set to ${TIER_META[agentTier].label}` : "Could not update tier");
    setBusy(false);
  }, [agentId, agentTier, readOnly, portal]);

  const sttHealth = providerHealth(providers, resolved?.stt?.provider);
  const llmHealth = providerHealth(providers, resolved?.llm?.provider);
  const ttsHealth = providerHealth(providers, resolved?.tts?.provider);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Audio hardware rack"
        title="Voice & Models"
        description={
          readOnly
            ? "Resolved STT, LLM, and TTS stacks per tier — configured in Dev → Stack & tiers."
            : "Customer-facing tier and resolved provider stack. Provider matrix is managed by your platform administrator."
        }
        actions={
          !readOnly && portal === "app" ? (
            <SkeuoButton variant="primary" size="sm" onClick={saveDefaultTier} loading={busy}>
              Save default tier
            </SkeuoButton>
          ) : undefined
        }
      />

      {status && <p className="text-sm text-text-muted" role="status">{status}</p>}

      <VoiceTierSelector
        value={selectedTier}
        onChange={(t) => {
          setSelectedTier(t);
          if (!readOnly) setAgentTier(t);
        }}
        disabled={readOnly}
      />

      {!readOnly && agentTier !== normalizeTier(initialTier) && (
        <p className="text-xs text-text-muted">
          Agent default tier: <span className="font-mono text-accent-primary">{TIER_META[agentTier].label}</span>
          — click Save default tier to apply.
        </p>
      )}

      {tierRow?.error ? (
        <SkeuoPanel title="Stack resolution error" padding="md">
          <p className="text-sm text-status-warning">{tierRow.error}</p>
        </SkeuoPanel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <VoiceRackModule
            stage="stt"
            provider={resolved?.stt?.provider}
            model={resolved?.stt?.model}
            language={resolved?.language}
            healthy={sttHealth.healthy}
            configured={sttHealth.configured}
          />
          <VoiceRackModule
            stage="llm"
            provider={resolved?.llm?.provider}
            model={resolved?.llm?.model}
            language={resolved?.language}
            healthy={llmHealth.healthy}
            configured={llmHealth.configured}
          />
          <VoiceRackModule
            stage="tts"
            provider={resolved?.tts?.provider}
            model={resolved?.tts?.model}
            language={resolved?.language}
            healthy={ttsHealth.healthy}
            configured={ttsHealth.configured}
          />
        </div>
      )}

      <SkeuoPanel title="Resolution metadata" padding="md" className="lg:col-span-3">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <dt className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Config mode</dt>
            <dd className="mt-1 font-mono text-text">{configMode || "—"}</dd>
          </div>
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <dt className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Combination</dt>
            <dd className="mt-1 font-mono text-xs text-text truncate">
              {tierRow?.combination_id || resolved?.combination_id || "—"}
            </dd>
          </div>
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <dt className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Preview tier</dt>
            <dd className="mt-1 font-mono text-text">{TIER_META[selectedTier].label}</dd>
          </div>
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <dt className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Providers probed</dt>
            <dd className="mt-1 font-mono text-text">{providers.length}</dd>
          </div>
        </dl>
        {readOnly && (
          <p className="mt-4 text-sm text-text-muted">
            To change STT / LLM / TTS assignments, use{" "}
            <span className="font-mono text-accent-primary">Dev → Stack & tiers</span> and promote to this environment.
          </p>
        )}
      </SkeuoPanel>
    </div>
  );
}
