"use client";

import { useCallback, useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { assembleRawPreview, type BrainSection } from "@/lib/brain-utils";
import { TEST_STUDIO_SESSION_ID } from "@/lib/test-studio-stack";
import { invalidateTtsConfigCache } from "@/lib/voice/tts-config";
import { notifyTestStudioVoiceSaved } from "@/lib/voice/voice-runtime-events";

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

export type CallEndPolicyState = {
  allowedReasons: string[];
  farewell: string;
};

export const CALL_END_REASONS: { id: string; label: string }[] = [
  { id: "goodbye", label: "Goodbye / hang up / don't call" },
  { id: "firm_refusal", label: "Firm refusal after you stopped pushing" },
  { id: "goal_complete", label: "Goal complete, nothing else" },
  { id: "abuse", label: "Abuse" },
  { id: "out_of_scope", label: "Still off-scope after one redirect" },
];

export const DEFAULT_CALL_END_FAREWELL: Record<string, string> = {
  "te-IN": "Sare, time ichinanduku thanks. Good day.",
  "en-IN": "Thank you for your time. Goodbye.",
  "hi-IN": "Time dene ke liye dhanyavaad. Alvida.",
};

export function defaultCallEndPolicy(language: string): CallEndPolicyState {
  return {
    allowedReasons: CALL_END_REASONS.map((r) => r.id),
    farewell: DEFAULT_CALL_END_FAREWELL[language] || DEFAULT_CALL_END_FAREWELL["en-IN"],
  };
}

export function normalizeCallEndPolicyState(raw: unknown, language: string): CallEndPolicyState {
  const fallback = defaultCallEndPolicy(language);
  if (!raw || typeof raw !== "object") return fallback;
  const o = raw as Record<string, unknown>;
  const reasons = Array.isArray(o.allowedReasons)
    ? (o.allowedReasons as unknown[]).map((id) => String(id)).filter(Boolean)
    : fallback.allowedReasons;
  const farewell = String(o.farewell || "").trim();
  const isStock = !farewell || Object.values(DEFAULT_CALL_END_FAREWELL).includes(farewell);
  return {
    allowedReasons: reasons.length ? reasons : fallback.allowedReasons,
    farewell: isStock ? fallback.farewell : farewell,
  };
}

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
  callEndPolicy: CallEndPolicyState;
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

function spokenStyleMatchesLanguage(style: string, language: string): boolean {
  const s = (style || "").toLowerCase();
  if (!s) return true;
  const lang = (language || "").toLowerCase();
  if (lang.startsWith("en") && (s.includes("spoken telugu") || s.includes("tanglish"))) return false;
  if (lang.startsWith("hi") && s.includes("spoken telugu")) return false;
  if (lang.startsWith("te") && s.includes("spoken indian english") && !s.includes("telugu")) return false;
  return true;
}
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

export function useTestStudioFineTune(agentId: string, language: string, portal: "app" | "dev" = "app") {
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
    callEndPolicy: defaultCallEndPolicy(language),
  });
  const [optimizerMeta, setOptimizerMeta] = useState<{
    compiledVersion?: number;
    optimizerModel?: string;
    tokensSaved?: number;
    rawTokenEstimate?: number;
    savedLanguage?: string;
    agentName?: string;
    detectedRole?: string;
    responseStyle?: string;
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
        fetch(`/api/instructions?sessionId=${encodeURIComponent(sessionId)}${portal === "dev" ? "&includeCompiled=true" : ""}`, { credentials: "include" }),
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
          responseStyle: spokenStyleMatchesLanguage(j.responseStyle || j.style || "", language)
            ? j.responseStyle || j.style || ""
            : "",
          brainPrompt: j.brainPrompt || "",
          estimatedTokens: Number(j.estimatedTokens || 0),
          budgetTokens: Number(j.budgetTokens || 2000),
          headroom: Number(j.headroom || 0),
          customBrainPrompt: Boolean(j.customBrainPrompt),
          cacheEligible: Boolean(j.cacheEligible),
          callEndPolicy: normalizeCallEndPolicyState(j.callEndPolicy, language),
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
          savedLanguage: j.language,
          agentName: j.optimizerReport?.agent_name,
          detectedRole: j.optimizerReport?.detected_role,
          responseStyle: j.style,
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
  }, [agentId, language, sessionId, portal]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setInstructions((p) => {
      const current = p.callEndPolicy?.farewell || "";
      const isDefault = Object.values(DEFAULT_CALL_END_FAREWELL).includes(current) || !current.trim();
      if (!isDefault) return p;
      const next = defaultCallEndPolicy(language);
      if (current === next.farewell && p.callEndPolicy?.allowedReasons?.length) return p;
      return { ...p, callEndPolicy: { ...(p.callEndPolicy || next), farewell: next.farewell } };
    });
  }, [language]);

  const saveInstructions = useCallback(async () => {
    const briefWords = countWords(instructions.agentBrief);
    if (briefWords > limits.agentBriefMaxWords || instructions.agentBrief.length > limits.agentBriefMax) {
      setStatus(
        `Agent brief is ${briefWords} words / ${instructions.agentBrief.length} chars (max ${limits.agentBriefMaxWords} words / ${limits.agentBriefMax} chars). Shorten it before saving.`
      );
      return false;
    }
    if (!instructions.agentBrief.trim()) {
      setStatus("Write a short agent brief first — company, agent name, and what they should do on the call.");
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
          responseStyle: spokenStyleMatchesLanguage(instructions.responseStyle, language)
            ? instructions.responseStyle || undefined
            : undefined,
          brainPromptBudgetTokens: runtime.brainPromptBudgetTokens,
          language_code: language,
          callEndPolicy: normalizeCallEndPolicyState(instructions.callEndPolicy, language),
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
        callEndPolicy: normalizeCallEndPolicyState(j.callEndPolicy, language),
      }));
      setOptimizerMeta({
        compiledVersion: j.compiledVersion,
        optimizerModel: j.optimizerReport?.optimizer_model,
        tokensSaved: j.tokensSaved ?? j.optimizerReport?.tokens_saved,
        rawTokenEstimate: j.rawTokenEstimate,
        savedLanguage: j.language || language,
        agentName: j.optimizerReport?.agent_name,
        detectedRole: j.optimizerReport?.detected_role,
        responseStyle: j.responseStyle || j.style,
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

  const saveCallEndPolicy = useCallback(async () => {
    setSaving(true);
    setStatus("Saving call end policy…");
    try {
      const r = await fetch("/api/instructions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          sessionId,
          language_code: language,
          callEndPolicy: normalizeCallEndPolicyState(instructions.callEndPolicy, language),
          reassembleOnly: true,
        }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        setStatus(apiErrorMessage(j, `Call-end save failed (${r.status})`));
        return false;
      }
      setInstructions((prev) => ({
        ...prev,
        estimatedTokens: Number(j.estimatedTokens || prev.estimatedTokens),
        budgetTokens: Number(j.budgetTokens || prev.budgetTokens),
        headroom: Number(j.headroom || prev.headroom),
        cacheEligible: Boolean(j.cacheEligible),
        callEndPolicy: normalizeCallEndPolicyState(j.callEndPolicy, language),
      }));
      setOptimizerMeta((prev) => ({ ...prev, savedLanguage: j.language || language }));
      setStatus("Call-end policy saved into the compiled brain");
      return true;
    } catch {
      setStatus("Call-end save failed — network error");
      return false;
    } finally {
      setSaving(false);
    }
  }, [instructions.callEndPolicy, language, sessionId]);

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
    if (typeof patch.ttsSpeaker === "string" && patch.ttsSpeaker) {
      invalidateTtsConfigCache();
      notifyTestStudioVoiceSaved(patch.ttsSpeaker);
    }
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
      callEndPolicy: defaultCallEndPolicy(language),
    }));
    setStatus("Loaded factory default — click Create agent script to apply");
  }, [language]);

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
    saveCallEndPolicy,
    saveRuntime,
    saveAll,
    clearSession,
    loadFactoryDefault,
    importFromAgentDraft,
  };
}
