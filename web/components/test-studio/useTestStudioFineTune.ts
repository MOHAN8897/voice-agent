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
  behaviourInstructions: string;
  businessInstructions: string;
  responseStyle: string;
  brainPrompt: string;
  estimatedTokens: number;
  budgetTokens: number;
  headroom: number;
  customBrainPrompt: boolean;
};

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
    behaviourInstructions: "",
    businessInstructions: "",
    responseStyle: "",
    brainPrompt: "",
    estimatedTokens: 0,
    budgetTokens: 2000,
    headroom: 2000,
    customBrainPrompt: false,
  });
  const [effectivePreview, setEffectivePreview] = useState("");
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
          behaviourInstructions: j.behaviour || "",
          businessInstructions: j.business || "",
          responseStyle: j.responseStyle || j.style || "",
          brainPrompt: j.brainPrompt || "",
          estimatedTokens: Number(j.estimatedTokens || 0),
          budgetTokens: Number(j.budgetTokens || 2000),
          headroom: Number(j.headroom || 0),
          customBrainPrompt: Boolean(j.customBrainPrompt),
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

      const effR = await fetch(
        `/api/prompt/effective?sessionId=${encodeURIComponent(sessionId)}&language_code=${encodeURIComponent(language)}&transcript=${encodeURIComponent("Hello")}`,
        { credentials: "include" }
      );
      if (effR.ok) {
        const j = await effR.json();
        setEffectivePreview(j.compiledBrainPrompt || j.brainPrompt || "");
        setOptimizerMeta({
          compiledVersion: j.compiledVersion,
          optimizerModel: j.optimizerReport?.optimizer_model,
          tokensSaved: j.tokensSaved,
          rawTokenEstimate: j.rawTokenEstimate,
        });
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
    setStatus("Saving prompts… (may take a few seconds while compiling)");
    try {
      const r = await fetch("/api/instructions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          sessionId,
          behaviourInstructions: instructions.behaviourInstructions,
          businessInstructions: instructions.businessInstructions,
          responseStyle: instructions.responseStyle || undefined,
          brainPromptBudgetTokens: runtime.brainPromptBudgetTokens,
          language_code: language,
        }),
      });
      if (!r.ok) {
        let msg = "Prompt save failed";
        try {
          const j = await r.json();
          msg = j.detail?.error?.message || j.detail?.message || msg;
        } catch {
          msg = `${msg} (${r.status})`;
        }
        setStatus(msg);
        return false;
      }
      const j = await r.json();
      setInstructions((prev) => ({
        ...prev,
        behaviourInstructions: j.behaviour ?? prev.behaviourInstructions,
        businessInstructions: j.business ?? prev.businessInstructions,
        responseStyle: j.responseStyle ?? prev.responseStyle,
        estimatedTokens: j.estimatedTokens,
        budgetTokens: j.budgetTokens,
        headroom: j.headroom,
      }));
      setEffectivePreview(j.compiledBrainPrompt || j.brainPromptFull || j.brainPrompt || "");
      setOptimizerMeta({
        compiledVersion: j.compiledVersion,
        optimizerModel: j.optimizerReport?.optimizer_model,
        tokensSaved: j.tokensSaved ?? j.optimizerReport?.tokens_saved,
        rawTokenEstimate: j.rawTokenEstimate,
      });
      setStatus(
        j.compiledVersion
          ? `Prompts compiled (v${j.compiledVersion}) — saved for test session`
          : "Prompts saved for test session"
      );
      return true;
    } catch {
      setStatus("Prompt save failed — network error");
      return false;
    }
  }, [instructions, runtime.brainPromptBudgetTokens, sessionId, language]);

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
      behaviourInstructions: "",
      businessInstructions: "",
    }));
    setStatus("Loaded factory default — click Save prompts to apply");
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
      businessInstructions: business,
    }));
    setStatus("Imported agent draft into business instructions — Save prompts to apply");
  }, [agentMeta.draftSections]);

  const refreshEffectivePreview = useCallback(async () => {
    const r = await fetch(
      `/api/prompt/effective?sessionId=${encodeURIComponent(sessionId)}&language_code=${encodeURIComponent(language)}`,
      { credentials: "include" }
    );
    if (r.ok) {
      const j = await r.json();
      setEffectivePreview(j.compiledBrainPrompt || j.brainPrompt || "");
      setOptimizerMeta({
        compiledVersion: j.compiledVersion,
        optimizerModel: j.optimizerReport?.optimizer_model,
        tokensSaved: j.tokensSaved,
        rawTokenEstimate: j.rawTokenEstimate,
      });
      setInstructions((prev) => ({
        ...prev,
        estimatedTokens: j.estimatedTokens,
        budgetTokens: j.budgetTokens,
        headroom: j.headroom,
      }));
    }
  }, [language, sessionId]);

  return {
    sessionId,
    catalog,
    runtime,
    setRuntime,
    instructions,
    setInstructions,
    effectivePreview,
    optimizerMeta,
    agentMeta,
    status,
    loading,
    load,
    saveInstructions,
    saveRuntime,
    saveAll,
    clearSession,
    loadFactoryDefault,
    importFromAgentDraft,
    refreshEffectivePreview,
  };
}
