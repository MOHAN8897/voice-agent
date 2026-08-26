import { AgentVoiceModelsPanel } from "@/components/voice/AgentVoiceModelsPanel";
import { ConsolePage } from "@/components/console/ConsolePage";
import { apiGet } from "@/lib/api";

type TierRow = {
  tier: string;
  combination_id?: string;
  preview?: {
    stt?: { provider?: string; model?: string };
    llm?: { provider?: string; model?: string };
    tts?: { provider?: string; model?: string };
    language?: string;
  };
  error?: string;
};

export default async function DevAgentVoicePage({ params }: { params: { id: string } }) {
  let defaultTier = "medium";
  let tiers: TierRow[] = [];
  let providers: Array<{ id: string; healthy?: boolean; configured?: boolean }> = [];
  let configMode = "frontend";

  try {
    const agent = await apiGet<{ agent?: { default_tier?: string } }>(`/api/agents/${params.id}`);
    defaultTier = agent.agent?.default_tier || "medium";
  } catch {
    /* */
  }

  try {
    const tierData = await apiGet<{ tiers?: TierRow[]; config_mode?: string }>("/api/tiers");
    tiers = tierData.tiers || [];
    configMode = tierData.config_mode || "frontend";
  } catch {
    tiers = [];
  }

  try {
    const statusData = await apiGet<{ providers?: Array<{ id: string; healthy?: boolean; configured?: boolean }> }>(
      "/api/providers/status"
    );
    providers = statusData.providers || [];
  } catch {
    providers = [];
  }

  return (
    <ConsolePage>
      <AgentVoiceModelsPanel
        agentId={params.id}
        initialTier={defaultTier}
        tiers={tiers}
        providers={providers}
        configMode={configMode}
        readOnly
        portal="dev"
      />
    </ConsolePage>
  );
}
