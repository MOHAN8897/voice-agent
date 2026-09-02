"use client";

import { useCallback, useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { assembleRawPreview, type BrainSection } from "@/lib/brain-utils";
import { TEST_STUDIO_SESSION_ID } from "@/lib/test-studio-stack";

/** Keys that must be changed via voicePresetId, not individually. */
const VOICE_BUNDLED_KEYS = new Set([
  "ttsPace",
  "ttsTemperature",
  "sttSilenceMs",
  "sttThreshold",
  "sttStreamType",
  "bargeMinWords",
  "bargeRequireVad",
  "ttsMinBuffer",
  "ttsMaxChunk",
]);

const RUNTIME_SAVE_KEYS = new Set([
  "voicePresetId",
  "sttModel",
  "sttMode",
  "sttLanguage",
  "ttsModel",
  "ttsSpeaker",
  "ttsCodec",
  "ttsBitrate",
  "ttsSampleRate",
  "openaiModel",
  "openaiTemperature",
  "openaiReasoningEffort",
  "openaiMaxTokens",
  "brainPromptBudgetTokens",
  ...VOICE_BUNDLED_KEYS,
]);

export type InstructionsState = {
  agentBrief: string;
  agentScript: string;
  behaviourInstructions: string;
  businessInstructions: string;
  responseStyle: string;
  brainPrompt: string;
  estimatedTokens: number;
  budgetTokens: number;
  headroom: number;
  customBrainPrompt: boolean;
  cacheEligible?: boolean;
};

export type PromptLimits = {
  agentBriefMax: number;
  agentBriefMaxWords: number;
  recommendedAgentBriefWords: number;
  behaviourMax: number;
  businessMax: number;
  behaviourMaxWords: number;
  businessMaxWords: number;
  recommendedBehaviourWords: number;
  recommendedBusinessWords: number;
  cacheMinTokens: number;
  memoryHeadroomTokens: number;
};

const DEFAULT_LIMITS: PromptLimits = {
  agentBriefMax: 1200,
  agentBriefMaxWords: 180,
  recommendedAgentBriefWords: 80,
  behaviourMax: 2000,
  businessMax: 2400,
  behaviourMaxWords: 280,
  businessMaxWords: 320,
  recommendedBehaviourWords: 180,
  recommendedBusinessWords: 220,
  cacheMinTokens: 1024,
  memoryHeadroomTokens: 300,
};

function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const j = payload as Record<string, unknown>;
  const detail = j.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const err = d.error;
    if (err && typeof err === "object" && typeof (err as { message?: string }).message === "string") {
      return (err as { message: string }).message;
    }
    if (typeof d.message === "string") return d.message;
  }
  if (typeof j.message === "string") return j.message;
  return fallback;
}

export type RuntimeState = Record<string, unknown>;

type Catalog = {
  openai?: {
    defaults?: Record<string, unknown>;
    allowedModels?: string[];
    modelLabels?: Record<string, string>;
    temperature?: number[];
    maxTokens?: number[];
    brainPromptBudget?: number[];
    reasoningEfforts?: string[];
  };
  tts?: {
    voicePresets?: { id: string; label: string }[];
    speakersV3?: string[];
  };
};

export function useTestStudioFineTune(agentId: string, language: string) {
  const sessionId = TEST_STUDIO_SESSION_ID;
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [runtime, setRuntime] = useState<RuntimeState>({});
  const [instructions, setInstructions] = useState<InstructionsState>({
    agentBrief: "",
    agentScript: "",
    behaviourInstructions: "",
    businessInstructions: "",
    responseStyle: "",
    brainPrompt: "",
    estimatedTokens: 0,
    budgetTokens: 2000,
    headroom: 2000,
    customBrainPrompt: false,
  });
  const [optimizerMeta, setOptimizerMeta] = useState<{
    compiledVersion?: number;
    optimizerModel?: string;
    tokensSaved?: number;
    rawTokenEstimate?: number;
  }>({});
  const [agentMeta, setAgentMeta] = useState<{
    name?: string;
    publishedVersion?: string;
    versionsCount?: number;
    draftSections?: BrainSection[];
  }>({});
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [limits, setLimits] = useState<PromptLimits>(DEFAULT_LIMITS);

  const load = useCallback(async () => {
    setLoading(true);
    setStatus("");
    try {
      const [catR, runR, insR, agentR, brainR] = await Promise.all([
        fetch("/api/settings/catalog", { credentials: "include" }),
        fetch(`/api/settings/runtime?sessionId=${encodeURIComponent(sessionId)}`, { credentials: "include" }),
        fetch(`/api/instructions?sessionId=${encodeURIComponent(sessionId)}&includeCompiled=true`, { credentials: "include" }),
        fetch(`/api/agents/${agentId}`, { credentials: "include" }),
        fetch(`/api/agents/${agentId}/business-brain`, { credentials: "include" }),
      ]);

      if (catR.ok) setCatalog(await catR.json());

      if (runR.ok) {
        const j = await runR.json();
        setRuntime(j.values || {});
      }

      if (insR.ok) {
        const j = await insR.json();
        setInstructions({
          agentBrief: j.agentBrief || "",
          agentScript: j.agentScript || "",
          behaviourInstructions: j.behaviour || "",
          businessInstructions: j.business || "",
          responseStyle: j.responseStyle || j.style || "",
          brainPrompt: j.brainPrompt || "",
          estimatedTokens: Number(j.estimatedTokens || 0),
          budgetTokens: Number(j.budgetTokens || 2000),
          headroom: Number(j.headroom || 0),
          customBrainPrompt: Boolean(j.customBrainPrompt),
          cacheEligible: Boolean(j.cacheEligible),
        });
        const lim = j.limits || {};
        setLimits({
          agentBriefMax: Number(lim.agentBriefMax || DEFAULT_LIMITS.agentBriefMax),
          agentBriefMaxWords: Number(lim.agentBriefMaxWords || DEFAULT_LIMITS.agentBriefMaxWords),
          recommendedAgentBriefWords: Number(
            lim.recommendedAgentBriefWords || DEFAULT_LIMITS.recommendedAgentBriefWords
          ),
          behaviourMax: Number(lim.behaviourMax || DEFAULT_LIMITS.behaviourMax),
          businessMax: Number(lim.businessMax || DEFAULT_LIMITS.businessMax),
          behaviourMaxWords: Number(lim.behaviourMaxWords || DEFAULT_LIMITS.behaviourMaxWords),
          businessMaxWords: Number(lim.businessMaxWords || DEFAULT_LIMITS.businessMaxWords),
          recommendedBehaviourWords: Number(
            lim.recommendedBehaviourWords || DEFAULT_LIMITS.recommendedBehaviourWords
          ),
          recommendedBusinessWords: Number(
            lim.recommendedBusinessWords || DEFAULT_LIMITS.recommendedBusinessWords
          ),
          cacheMinTokens: Number(j.cacheMinTokens || lim.cacheMinTokens || DEFAULT_LIMITS.cacheMinTokens),
          memoryHeadroomTokens: Number(
            lim.memoryHeadroomTokens || DEFAULT_LIMITS.memoryHeadroomTokens
          ),
        });
        setOptimizerMeta({
          compiledVersion: j.compiledVersion,
          optimizerModel: j.optimizerReport?.optimizer_model,
          tokensSaved: j.optimizerReport?.tokens_saved,
          rawTokenEstimate: j.rawTokenEstimate,
        });
      }

      if (agentR.ok) {
        const j = await agentR.json();
        setAgentMeta((m) => ({
          ...m,
          name: j.agent?.name,
          publishedVersion: j.agent?.active_compiled_brain_version,
        }));
      }

      if (brainR.ok) {
        const j = await brainR.json();
        const sections = ensureArray<BrainSection>(j.draft?.sections);
        setAgentMeta((m) => ({
          ...m,
          draftSections: sections,
          versionsCount: j.versions_count,
          publishedVersion: j.published?.version_id || m.publishedVersion,
        }));
      }
    } catch {
      setStatus("Failed to load fine-tune settings");
    } finally {
      setLoading(false);
    }
  }, [agentId, language, sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  const saveInstructions = useCallback(async () => {
    const briefWords = countWords(instructions.agentBrief);
    if (briefWords > limits.agentBriefMaxWords || instructions.agentBrief.length > limits.agentBriefMax) {
      setStatus(
        `Agent brief is ${briefWords} words / ${instructions.agentBrief.length} chars (max ${limits.agentBriefMaxWords} words / ${limits.agentBriefMax} chars). Shorten it before saving.`
      );
      return false;
    }
    if (!instructions.agentBrief.trim()) {
      setStatus("Write a short agent brief first — e.g. company name, agent name, and what the telecaller should do.");
      return false;
    }
    setSaving(true);
    setStatus("Creating agent script… GPT expanding your brief (up to ~25s)");
    try {
      const r = await fetch("/api/instructions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          sessionId,
          agentBrief: instructions.agentBrief,
          responseStyle: instructions.responseStyle || undefined,
          brainPromptBudgetTokens: runtime.brainPromptBudgetTokens,
          language_code: language,
        }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        setStatus(apiErrorMessage(j, `Agent script creation failed (${r.status})`));
        return false;
      }
      setInstructions((prev) => ({
        ...prev,
        agentBrief: j.agentBrief ?? prev.agentBrief,
        agentScript: j.agentScript ?? prev.agentScript,
        responseStyle: j.responseStyle ?? prev.responseStyle,
        brainPrompt: j.compiledBrainPrompt || j.brainPromptFull || prev.brainPrompt,
        estimatedTokens: j.estimatedTokens,
        budgetTokens: j.budgetTokens,
        headroom: j.headroom,
        cacheEligible: Boolean(j.cacheEligible),
      }));
      setOptimizerMeta({
        compiledVersion: j.compiledVersion,
        optimizerModel: j.optimizerReport?.optimizer_model,
        tokensSaved: j.tokensSaved ?? j.optimizerReport?.tokens_saved,
        rawTokenEstimate: j.rawTokenEstimate,
      });
      const cacheNote = j.cacheEligible
        ? `cache ON (≥${j.cacheMinTokens || 1024} tokens)`
        : `cache OFF — compiled ${j.estimatedTokens} tokens, need ≥${j.cacheMinTokens || 1024}`;
      setStatus(
        j.compiledVersion
          ? `Agent script v${j.compiledVersion} created and saved · ${j.estimatedTokens} tokens · ${cacheNote}`
          : `Agent script saved · ${cacheNote}`
      );
      return true;
    } catch {
      setStatus("Agent script creation failed — network error");
      return false;
    } finally {
      setSaving(false);
    }
  }, [instructions, limits, runtime.brainPromptBudgetTokens, sessionId, language]);

  const saveRuntime = useCallback(async () => {
    setStatus("Saving runtime…");
    const patch: Record<string, unknown> = { sessionId };
    for (const [key, val] of Object.entries(runtime)) {
      if (!RUNTIME_SAVE_KEYS.has(key) || val == null || val === "") continue;
      patch[key] = val;
    }
    const bundled = Object.keys(patch).some((k) => VOICE_BUNDLED_KEYS.has(k));
    if (bundled && patch.voicePresetId == null) {
      for (const k of VOICE_BUNDLED_KEYS) delete patch[k];
    }
    if (Object.keys(patch).length <= 1) {
      setStatus("No runtime overrides to save");
      return true;
    }
    const r = await fetch("/api/settings/runtime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(patch),
    });
    if (!r.ok) {
      let msg = "Runtime save failed";
      try {
        const j = await r.json();
        msg = j.detail?.error?.message || msg;
      } catch {
        msg = `${msg} (${r.status})`;
      }
      setStatus(msg);
      return false;
    }
    setStatus("Runtime saved for test session");
    return true;
  }, [runtime, sessionId]);

  const saveAll = useCallback(async () => {
    await saveRuntime();
    await saveInstructions();
  }, [saveInstructions, saveRuntime]);

  const clearSession = useCallback(async () => {
    setStatus("Clearing session…");
    await Promise.all([
      fetch(`/api/settings/runtime?sessionId=${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
        credentials: "include",
      }),
      fetch(`/api/instructions?sessionId=${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
        credentials: "include",
      }),
    ]);
    await load();
    setStatus("Session overrides cleared");
  }, [load, sessionId]);

  const loadFactoryDefault = useCallback(async () => {
    const r = await fetch("/api/instructions/default", { credentials: "include" });
    if (!r.ok) return;
    const j = await r.json();
    setInstructions((prev) => ({
      ...prev,
      brainPrompt: j.brainPrompt || "",
      agentBrief: "",
      agentScript: "",
      behaviourInstructions: "",
      businessInstructions: "",
    }));
    setStatus("Loaded factory default — click Create agent script to apply");
  }, []);

  const importFromAgentDraft = useCallback(() => {
    const sections = agentMeta.draftSections;
    if (!sections?.length) {
      setStatus("No agent draft sections found");
      return;
    }
    const business = assembleRawPreview(sections);
    setInstructions((prev) => ({
      ...prev,
      agentBrief: business,
    }));
    setStatus("Imported agent draft into agent brief — Create agent script to apply");
  }, [agentMeta.draftSections]);

  return {
    sessionId,
    catalog,
    runtime,
    setRuntime,
    instructions,
    setInstructions,
    optimizerMeta,
    agentMeta,
    status,
    loading,
    saving,
    limits,
    load,
    saveInstructions,
    saveRuntime,
    saveAll,
    clearSession,
    loadFactoryDefault,
    importFromAgentDraft,
  };
}
