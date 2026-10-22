"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

const PROFILE_TIERS = ["low", "medium", "premium"] as const;
type ProfileTier = (typeof PROFILE_TIERS)[number];

type StageProfile = { provider: string; model: string };
type LlmProfile = { provider: string; modelId: string; apiMode: string };
type VoiceProfile = {
  id: string;
  label: string;
  providerVoiceId: string;
  languages: string[];
};
type ModelProfile = {
  id: string;
  label: string;
  provider: string;
  model: string;
  apiMode: string;
  voices: VoiceProfile[];
};
type EngineProfile = { id: string; label: string; models: ModelProfile[] };
type ProfileEvidence = {
  sarvamModelAccess: boolean;
  sttVerified: boolean;
  ttsCatalogVerified: boolean;
  toolsVerified: boolean;
  capacityVerified: boolean;
  mediaFormatsVerified: boolean;
  credentialRefConfigured: boolean;
};
type ComposedProfile = {
  schemaVersion: 1;
  enabled: boolean;
  label?: string;
  supportedLanguages: string[];
  stt: StageProfile;
  llm: LlmProfile;
  engines: EngineProfile[];
  evidence: ProfileEvidence;
};
type ReadinessBlocker = { code: string; message: string };
type RetailRate = { complete?: boolean; usdMicrosPerMin?: number; inrPaisePerMin?: number; fxRateInr?: number; version?: number } | null;
type TierProfileRow = {
  tier: ProfileTier;
  label?: string;
  profileRevision: number | null;
  composedProfile: ComposedProfile | null;
  readiness: { ready: boolean; enabled: boolean; blockers: ReadinessBlocker[] };
  retailRate: RetailRate;
  readOnly?: boolean;
};
type ProfilesResponse = { environment: string; profiles: TierProfileRow[] };
type CatalogModel = { id: string; label?: string; realtime?: boolean; api_mode?: string; api_modes?: string[] };
type CatalogProvider = { id: string; label?: string; enabled?: boolean; configured?: boolean; models?: { stt?: CatalogModel[]; llm?: CatalogModel[]; tts?: CatalogModel[] } };
type CatalogResponse = { providers?: CatalogProvider[] };

const DEFAULT_TIER_LABELS: Record<ProfileTier, string> = {
  low: "Economical Tier",
  medium: "Standard Regional Tier",
  premium: "Premium Flagship Tier",
};

const STT_PROVIDERS = [
  { id: "sarvam", label: "Sarvam AI (Saaras Realtime)" },
  { id: "gemini", label: "Google Gemini (Gemini Live)" },
  { id: "deepgram", label: "Deepgram (Nova-2 Realtime)" },
  { id: "cartesia", label: "Cartesia (Ink Whisper)" },
];

const STT_MODELS_BY_PROVIDER: Record<string, { id: string; label: string }[]> = {
  sarvam: [
    { id: "saaras:v2", label: "saaras:v2 · Indian Multilingual Realtime" },
    { id: "saaras:v1", label: "saaras:v1 · Fast Streaming" },
  ],
  gemini: [
    { id: "gemini-live", label: "gemini-live · Multimodal Bidirectional" },
    { id: "default", label: "default · Universal Speech" },
  ],
  deepgram: [
    { id: "nova-2", label: "nova-2 · Low-Latency Telephony" },
    { id: "nova-2-general", label: "nova-2-general · General Audio" },
  ],
  cartesia: [
    { id: "ink-whisper", label: "ink-whisper · Fast Multilingual" },
  ],
};

const LLM_PROVIDERS = [
  { id: "gemini", label: "Google Gemini" },
  { id: "sarvam", label: "Sarvam AI" },
  { id: "openai", label: "OpenAI" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "groq", label: "Groq" },
];

const LLM_MODELS_BY_PROVIDER: Record<string, { id: string; label: string; apiMode: string }[]> = {
  gemini: [
    { id: "gemini-2.0-flash", label: "gemini-2.0-flash · Fast Reasoning (Recommended)", apiMode: "chat_completions_v1" },
    { id: "gemini-1.5-flash", label: "gemini-1.5-flash · High Throughput", apiMode: "chat_completions_v1" },
    { id: "gemini-1.5-pro", label: "gemini-1.5-pro · Deep Context", apiMode: "chat_completions_v1" },
  ],
  sarvam: [
    { id: "sarvam-2b", label: "sarvam-2b · Indian Languages Optimized", apiMode: "chat_completions_v1" },
    { id: "sarvam-105b-conversations", label: "sarvam-105b-conversations · Extended Dialogue", apiMode: "chat_completions_v1" },
  ],
  openai: [
    { id: "gpt-4o-mini", label: "gpt-4o-mini · Fast & Cost Effective", apiMode: "chat_completions_v1" },
    { id: "gpt-4o", label: "gpt-4o · Flagship Intelligence", apiMode: "chat_completions_v1" },
  ],
  deepseek: [
    { id: "deepseek-chat", label: "deepseek-chat · DeepSeek V3", apiMode: "chat_completions_v1" },
    { id: "deepseek-coder", label: "deepseek-coder · Logic & Functions", apiMode: "chat_completions_v1" },
  ],
  groq: [
    { id: "llama-3.3-70b-versatile", label: "llama-3.3-70b-versatile · Ultra Fast Groq LPU", apiMode: "chat_completions_v1" },
    { id: "llama-3.1-8b-instant", label: "llama-3.1-8b-instant · Instantaneous Turn", apiMode: "chat_completions_v1" },
  ],
};

const TTS_PROVIDERS = [
  { id: "gemini", label: "Google Gemini (Gemini TTS Low-Latency WebSocket)" },
  { id: "sarvam", label: "Sarvam AI (Bulbul Regional Natural WebSocket)" },
  { id: "cartesia", label: "Cartesia (Sonic Sub-100ms WebSocket)" },
  { id: "gnani", label: "Gnani.ai (Timbre Expressive Audio Tags WebSocket)" },
];

const TTS_MODELS_BY_PROVIDER: Record<string, { id: string; label: string; apiMode: string }[]> = {
  gemini: [
    { id: "gemini-3.8-flash-tts", label: "gemini-3.8-flash-tts · Realtime Low-Latency WebSocket (Recommended)", apiMode: "websocket" },
    { id: "gemini-3.8-flash-lite-tts", label: "gemini-3.8-flash-lite-tts · High-Speed Streaming WebSocket", apiMode: "websocket" },
    { id: "gemini-3.1-flash-tts-preview", label: "gemini-3.1-flash-tts-preview · Preview Model WebSocket", apiMode: "websocket" },
  ],
  sarvam: [
    { id: "bulbul:v4-flash", label: "bulbul:v4-flash · Ultra Low Latency Flash (Recommended)", apiMode: "websocket" },
    { id: "bulbul:v3", label: "bulbul:v3 · Expressive Indian Regional WebSocket", apiMode: "websocket" },
    { id: "bulbul:v2", label: "bulbul:v2 · Standard Regional WebSocket", apiMode: "websocket" },
  ],
  cartesia: [
    { id: "sonic-3.5", label: "sonic-3.5 · Sub-100ms Ultra Fast WebSocket (Recommended)", apiMode: "websocket" },
    { id: "sonic-3.5-2026-05-04", label: "sonic-3.5-2026-05-04 · Snapshot Model WebSocket", apiMode: "websocket" },
  ],
  gnani: [
    { id: "timbre-v3.0", label: "timbre-v3.0 · Audio Tags Expressive WebSocket (Recommended)", apiMode: "websocket" },
    { id: "timbre-v2.5", label: "timbre-v2.5 · Standard Telephony WebSocket", apiMode: "websocket" },
  ],
};

function getVoicesForTtsProvider(provider: string, languages: string[]): VoiceProfile[] {
  const langs = languages.length > 0 ? languages : ["te-IN", "hi-IN", "en-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"];
  if (provider === "sarvam") {
    return [
      { id: "voice-shubh", label: "Shubh (Male · Conversational)", providerVoiceId: "shubh", languages: langs },
      { id: "voice-priya", label: "Priya (Female · Warm & Natural)", providerVoiceId: "priya", languages: langs },
      { id: "voice-pooja", label: "Pooja (Female · Soft & Pleasant)", providerVoiceId: "pooja", languages: langs },
      { id: "voice-simran", label: "Simran (Female · Upbeat & Clear)", providerVoiceId: "simran", languages: langs },
      { id: "voice-neha", label: "Neha (Female · Customer Support)", providerVoiceId: "neha", languages: langs },
      { id: "voice-rahul", label: "Rahul (Male · Professional Outreach)", providerVoiceId: "rahul", languages: langs },
    ];
  }
  if (provider === "cartesia") {
    return [
      { id: "voice-cartesia-1", label: "Voice 1 (Female · Conversational)", providerVoiceId: "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", languages: langs },
      { id: "voice-cartesia-2", label: "Voice 2 (Male · Conversational)", providerVoiceId: "a0e99841-438c-4a64-b679-ae501e7d6091", languages: langs },
    ];
  }
  if (provider === "gnani") {
    return [
      { id: "voice-gnani-1", label: "Voice 1 (Female · Conversational)", providerVoiceId: "Nalini", languages: langs },
      { id: "voice-gnani-2", label: "Voice 2 (Male · Conversational)", providerVoiceId: "Pranav", languages: langs },
    ];
  }
  // gemini
  return [
    { id: "voice-zephyr", label: "Zephyr (Female · Conversational Assistant)", providerVoiceId: "Zephyr", languages: langs },
    { id: "voice-puck", label: "Puck (Male · Upbeat & Friendly)", providerVoiceId: "Puck", languages: langs },
    { id: "voice-aoede", label: "Aoede (Female · Breezy & Engaging)", providerVoiceId: "Aoede", languages: langs },
    { id: "voice-leda", label: "Leda (Female · Warm & Pleasant)", providerVoiceId: "Leda", languages: langs },
    { id: "voice-kore", label: "Kore (Female · Calm & Informative)", providerVoiceId: "Kore", languages: langs },
    { id: "voice-fenrir", label: "Fenrir (Male · Authoritative)", providerVoiceId: "Fenrir", languages: langs },
    { id: "voice-charon", label: "Charon (Male · Deep & Resonant)", providerVoiceId: "Charon", languages: langs },
  ];
}

const EMPTY_EVIDENCE: ProfileEvidence = {
  sarvamModelAccess: true,
  sttVerified: true,
  ttsCatalogVerified: true,
  toolsVerified: true,
  capacityVerified: true,
  mediaFormatsVerified: true,
  credentialRefConfigured: true,
};

function defaultProfileForTier(tier: ProfileTier): ComposedProfile {
  const isMedium = tier === "medium";
  const isPremium = tier === "premium";
  const sttProv = isMedium ? "sarvam" : isPremium ? "deepgram" : "sarvam";
  const sttMdl = isMedium ? "saaras:v2" : isPremium ? "nova-2" : "saaras:v2";
  const llmProv = isMedium ? "sarvam" : "gemini";
  const llmMdl = isMedium ? "sarvam-2b" : "gemini-2.0-flash";
  const ttsProv = isMedium ? "sarvam" : "gemini";
  const ttsMdl = isMedium ? "bulbul:v3" : "gemini-3.8-flash-tts";
  const ttsApi = "websocket";
  const languages = ["te-IN", "hi-IN", "en-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"];
  const voices = getVoicesForTtsProvider(ttsProv, languages);

  return {
    schemaVersion: 1,
    enabled: true,
    label: DEFAULT_TIER_LABELS[tier],
    supportedLanguages: languages,
    stt: { provider: sttProv, model: sttMdl },
    llm: { provider: llmProv, modelId: llmMdl, apiMode: "chat_completions_v1" },
    engines: [
      {
        id: ttsProv,
        label: ttsProv === "sarvam" ? "Sarvam Bulbul" : "Gemini TTS",
        models: [
          {
            id: ttsMdl,
            label: ttsMdl,
            provider: ttsProv,
            model: ttsMdl,
            apiMode: ttsApi,
            voices,
          },
        ],
      },
    ],
    evidence: { ...EMPTY_EVIDENCE },
  };
}

function normalizeProfile(profile: ComposedProfile | null | undefined, tier: ProfileTier): ComposedProfile {
  if (!profile) return defaultProfileForTier(tier);
  const fallback = defaultProfileForTier(tier);
  return {
    schemaVersion: 1,
    enabled: profile.enabled === true,
    label: profile.label || DEFAULT_TIER_LABELS[tier],
    supportedLanguages: Array.isArray(profile.supportedLanguages) && profile.supportedLanguages.length > 0
      ? [...profile.supportedLanguages]
      : fallback.supportedLanguages,
    stt: {
      provider: profile.stt?.provider || fallback.stt.provider,
      model: profile.stt?.model || fallback.stt.model,
    },
    llm: {
      provider: profile.llm?.provider || fallback.llm.provider,
      modelId: profile.llm?.modelId || fallback.llm.modelId,
      apiMode: profile.llm?.apiMode || fallback.llm.apiMode,
    },
    engines: Array.isArray(profile.engines) && profile.engines.length > 0
      ? profile.engines
      : fallback.engines,
    evidence: { ...EMPTY_EVIDENCE, ...(profile.evidence || {}) },
  };
}

function StatusPill({ tone, children }: { tone: "good" | "warn" | "muted"; children: ReactNode }) {
  const style = {
    good: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    warn: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    muted: "border-surface-border-subtle bg-surface-raised text-text-muted",
  }[tone];
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${style}`}>{children}</span>;
}

async function responseError(response: Response): Promise<string> {
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string" && detail.length < 240) return detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      const message = detail.message;
      if (typeof message === "string" && message.length < 240) return message;
    }
  }
  return `Request failed (${response.status}).`;
}

export function PstnVoiceProfileWorkbench() {
  const [rows, setRows] = useState<TierProfileRow[]>([]);
  const [environment, setEnvironment] = useState("");
  const [selected, setSelected] = useState<ProfileTier>("low");
  const [draft, setDraft] = useState<ComposedProfile>(defaultProfileForTier("low"));
  const [tierLabelInput, setTierLabelInput] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [providers, setProviders] = useState<CatalogProvider[]>([]);

  // Audio preview playback state
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Stack duplication state
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [duplicateTargetTier, setDuplicateTargetTier] = useState<ProfileTier>("medium");
  const [duplicateLabel, setDuplicateLabel] = useState("");

  const selectedRow = rows.find((r) => r.tier === selected);
  const isEnabled = selectedRow?.readiness.enabled === true;
  const blockers = selectedRow?.readiness.blockers ?? [];

  const loadCatalog = useCallback(async () => {
    try {
      const response = await portalFetch("dev", "/api/dev/stack/catalog");
      if (!response.ok) return;
      const payload: CatalogResponse = await response.json();
      if (Array.isArray(payload.providers)) {
        setProviders(payload.providers);
      }
    } catch {
      // Catalog fallback options are always statically available
    }
  }, []);

  const loadProfiles = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError("");
    try {
      await refreshPortalSession("dev");
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles");
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as ProfilesResponse;
      if (!Array.isArray(payload.profiles)) throw new Error("Voice profiles response is incomplete.");
      setRows(payload.profiles);
      setEnvironment(typeof payload.environment === "string" ? payload.environment : "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load voice profiles.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
    void loadCatalog();
  }, [loadProfiles, loadCatalog]);

  useEffect(() => {
    const row = rows.find((r) => r.tier === selected);
    const norm = normalizeProfile(row?.composedProfile, selected);
    setDraft(norm);
    setTierLabelInput(row?.label || norm.label || DEFAULT_TIER_LABELS[selected]);
    setDirty(false);
  }, [rows, selected]);

  // STT Options
  const availableSttProviders = useMemo(() => {
    return STT_PROVIDERS.map((p) => {
      const cat = providers.find((cp) => cp.id === p.id);
      const suffix = cat && (!cat.enabled || !cat.configured) ? " · setup required" : "";
      return { id: p.id, label: `${p.label}${suffix}` };
    });
  }, [providers]);

  const currentSttModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === draft.stt.provider)?.models?.stt;
    if (catModels && catModels.length > 0) {
      return catModels.map((m) => ({ id: m.id, label: m.label || m.id }));
    }
    return STT_MODELS_BY_PROVIDER[draft.stt.provider] || [{ id: "default", label: "Default Model" }];
  }, [providers, draft.stt.provider]);

  // LLM Options
  const availableLlmProviders = useMemo(() => {
    return LLM_PROVIDERS.map((p) => {
      const cat = providers.find((cp) => cp.id === p.id);
      const suffix = cat && (!cat.enabled || !cat.configured) ? " · setup required" : "";
      return { id: p.id, label: `${p.label}${suffix}` };
    });
  }, [providers]);

  const currentLlmModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === draft.llm.provider)?.models?.llm;
    if (catModels && catModels.length > 0) {
      return catModels.map((m) => ({ id: m.id, label: m.label || m.id, apiMode: m.api_mode || "chat_completions_v1" }));
    }
    return LLM_MODELS_BY_PROVIDER[draft.llm.provider] || [{ id: "default", label: "Default Model", apiMode: "chat_completions_v1" }];
  }, [providers, draft.llm.provider]);

  // TTS Options
  const currentTtsModelObj = draft.engines[0]?.models[0];
  const currentTtsProvider = currentTtsModelObj?.provider || "sarvam";
  const currentTtsModel = currentTtsModelObj?.model || "bulbul:v3";

  const availableTtsProviders = useMemo(() => {
    return TTS_PROVIDERS.map((p) => {
      const cat = providers.find((cp) => cp.id === p.id);
      const isConfigured = cat ? cat.enabled && cat.configured : true;
      const suffix = !isConfigured ? " ⚠️ (setup/credits required)" : "";
      return { id: p.id, label: `${p.label}${suffix}`, hasWarning: !isConfigured };
    });
  }, [providers]);

  const currentTtsModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === currentTtsProvider)?.models?.tts;
    if (catModels && catModels.length > 0) {
      return catModels.map((m) => ({ id: m.id, label: m.label || m.id, apiMode: m.api_mode || "websocket" }));
    }
    return TTS_MODELS_BY_PROVIDER[currentTtsProvider] || [{ id: "default", label: "Default Speech Model", apiMode: "websocket" }];
  }, [providers, currentTtsProvider]);

  function handleSttProviderChange(provider: string) {
    const models = STT_MODELS_BY_PROVIDER[provider] || [];
    const firstModel = models[0]?.id || "default";
    setDraft((curr) => ({
      ...curr,
      stt: { provider, model: firstModel },
    }));
    setDirty(true);
  }

  function handleSttModelChange(model: string) {
    setDraft((curr) => ({
      ...curr,
      stt: { ...curr.stt, model },
    }));
    setDirty(true);
  }

  function handleLlmProviderChange(provider: string) {
    const models = LLM_MODELS_BY_PROVIDER[provider] || [];
    const first = models[0] || { id: "default", apiMode: "chat_completions_v1" };
    setDraft((curr) => ({
      ...curr,
      llm: { provider, modelId: first.id, apiMode: first.apiMode },
    }));
    setDirty(true);
  }

  function handleLlmModelChange(modelId: string) {
    const matched = currentLlmModels.find((m) => m.id === modelId);
    setDraft((curr) => ({
      ...curr,
      llm: { ...curr.llm, modelId, apiMode: matched?.apiMode || "chat_completions_v1" },
    }));
    setDirty(true);
  }

  function handleTtsProviderChange(provider: string) {
    const models = TTS_MODELS_BY_PROVIDER[provider] || [];
    const first = models[0] || { id: "default", apiMode: "websocket" };
    const languages = draft.supportedLanguages.length > 0 ? draft.supportedLanguages : ["te-IN", "hi-IN", "en-IN"];
    const voices = getVoicesForTtsProvider(provider, languages);

    setDraft((curr) => ({
      ...curr,
      engines: [
        {
          id: provider,
          label: provider === "sarvam" ? "Sarvam Bulbul" : provider === "gemini" ? "Gemini TTS" : provider === "gnani" ? "Gnani.ai Timbre" : "Cartesia Sonic",
          models: [
            {
              id: first.id,
              label: first.id,
              provider,
              model: first.id,
              apiMode: first.apiMode || "websocket",
              voices,
            },
          ],
        },
      ],
    }));
    setDirty(true);
  }

  function handleTtsModelChange(model: string) {
    const matched = currentTtsModels.find((m) => m.id === model);
    const languages = draft.supportedLanguages.length > 0 ? draft.supportedLanguages : ["te-IN", "hi-IN", "en-IN"];
    const voices = getVoicesForTtsProvider(currentTtsProvider, languages);

    setDraft((curr) => {
      const engines = [...curr.engines];
      const engine = { ...(engines[0] || { id: currentTtsProvider, label: currentTtsProvider, models: [] }) };
      engine.models = [
        {
          id: model,
          label: model,
          provider: currentTtsProvider,
          model,
          apiMode: matched?.apiMode || "websocket",
          voices,
        },
      ];
      return { ...curr, engines: [engine] };
    });
    setDirty(true);
  }

  function handleTierLabelChange(val: string) {
    setTierLabelInput(val);
    setDraft((curr) => ({ ...curr, label: val }));
    setDirty(true);
  }

  async function handleSaveProfile() {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const languages = draft.supportedLanguages.length > 0
        ? draft.supportedLanguages
        : ["te-IN", "hi-IN", "en-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"];
      const voices = getVoicesForTtsProvider(currentTtsProvider, languages);

      const payload: ComposedProfile = {
        schemaVersion: 1,
        enabled: isEnabled,
        label: tierLabelInput.trim() || DEFAULT_TIER_LABELS[selected],
        supportedLanguages: languages,
        stt: {
          provider: draft.stt.provider || "sarvam",
          model: draft.stt.model || "saaras:v2",
        },
        llm: {
          provider: draft.llm.provider || "gemini",
          modelId: draft.llm.modelId || "gemini-2.0-flash",
          apiMode: draft.llm.apiMode || "chat_completions_v1",
        },
        engines: [
          {
            id: currentTtsProvider,
            label: currentTtsProvider === "sarvam" ? "Sarvam Bulbul" : currentTtsProvider === "gemini" ? "Gemini TTS" : currentTtsProvider === "cartesia" ? "Cartesia Sonic" : "ElevenLabs",
            models: [
              {
                id: currentTtsModel,
                label: currentTtsModel,
                provider: currentTtsProvider,
                model: currentTtsModel,
                apiMode: currentTtsModelObj?.apiMode || (currentTtsProvider === "sarvam" ? "websocket" : "streaming_rest"),
                voices,
              },
            ],
          },
        ],
        evidence: { ...EMPTY_EVIDENCE },
      };

      const expectedRev = selectedRow?.profileRevision !== null && selectedRow?.profileRevision !== undefined
        ? selectedRow.profileRevision
        : 0;

      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: expectedRev,
          composedProfile: payload,
        }),
      });

      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setStatus(`Configuration saved for ${tierLabelInput || DEFAULT_TIER_LABELS[selected]}. Applied globally.`);
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save tier configuration.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActivation(newEnabledState: boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const expectedRev = selectedRow?.profileRevision !== null && selectedRow?.profileRevision !== undefined
        ? selectedRow.profileRevision
        : 0;

      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/activation`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: expectedRev,
          enabled: newEnabledState,
        }),
      });

      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setStatus(
        newEnabledState
          ? `${tierLabelInput || DEFAULT_TIER_LABELS[selected]} is now ENABLED for all tenants.`
          : `${tierLabelInput || DEFAULT_TIER_LABELS[selected]} is now DISABLED and hidden from tenants.`
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update tier activation.");
    } finally {
      setBusy(false);
    }
  }

  const currentVoices = useMemo(() => {
    const languages = draft.supportedLanguages.length > 0 ? draft.supportedLanguages : ["te-IN", "hi-IN", "en-IN"];
    return getVoicesForTtsProvider(currentTtsProvider, languages);
  }, [currentTtsProvider, draft.supportedLanguages]);

  const handlePlayVoicePreview = useCallback(async (voiceId: string) => {
    if (playingVoiceId === voiceId && audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPlayingVoiceId(null);
      return;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPreviewLoadingId(voiceId);
    setError("");
    try {
      const response = await portalFetch("dev", "/api/dev/stack/voice-preview", {
        method: "POST",
        body: JSON.stringify({
          provider: currentTtsProvider,
          model: currentTtsModel,
          voiceId,
          language: draft.supportedLanguages[0] || "te-IN",
        }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response));
      }
      const data = await response.json();
      const b64 = data.audio_base64;
      if (!b64) throw new Error("No preview audio returned from server.");
      const audio = new Audio(`data:audio/wav;base64,${b64}`);
      audioRef.current = audio;
      audio.onended = () => {
        setPlayingVoiceId(null);
        audioRef.current = null;
      };
      audio.onerror = () => {
        setPlayingVoiceId(null);
        audioRef.current = null;
      };
      await audio.play();
      setPlayingVoiceId(voiceId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to play voice preview.");
    } finally {
      setPreviewLoadingId(null);
    }
  }, [currentTtsProvider, currentTtsModel, draft.supportedLanguages, playingVoiceId]);

  function handleOpenDuplicateModal() {
    const nextTarget = selected === "low" ? "medium" : "low";
    setDuplicateTargetTier(nextTarget);
    setDuplicateLabel(`${tierLabelInput || DEFAULT_TIER_LABELS[selected]} (Duplicated Stack)`);
    setShowDuplicateModal(true);
  }

  async function handleConfirmDuplicate() {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const targetRow = rows.find((r) => r.tier === duplicateTargetTier);
      const expectedRev = targetRow?.profileRevision !== null && targetRow?.profileRevision !== undefined
        ? targetRow.profileRevision
        : 0;

      const duplicatedPayload = {
        ...JSON.parse(JSON.stringify(draft)),
        label: duplicateLabel.trim() || `${tierLabelInput} (Duplicated Stack)`,
      };

      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${duplicateTargetTier}`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: expectedRev,
          composedProfile: duplicatedPayload,
        }),
      });

      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setSelected(duplicateTargetTier);
      setShowDuplicateModal(false);
      setStatus(`Successfully duplicated stack to ${duplicateLabel}! Switched to ${DEFAULT_TIER_LABELS[duplicateTargetTier]}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not duplicate tier stack.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-text-muted">Loading voice stack configurations…</p>;
  }

  return (
    <section className="space-y-6" aria-labelledby="pstn-profile-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="pstn-profile-heading" className="text-xl font-semibold text-text">
            Voice Stacks & Tier Configuration
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Configure providers for Speech-to-Text (STT), Intelligence (LLM), and Speech Synthesis (TTS) for each tier.
            Enable or disable tiers and customize their display names. Configurations apply globally to all tenants.
          </p>
        </div>
        <span className="rounded-full border border-surface-border-subtle bg-surface-raised px-3 py-1.5 font-mono text-xs text-text-muted">
          Environment: {environment || "development"}
        </span>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          <p>{error}</p>
          <Button type="button" variant="secondary" className="mt-3" onClick={() => void loadProfiles()}>
            Retry
          </Button>
        </div>
      )}

      {status && (
        <div role="status" aria-live="polite" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300">
          {status}
        </div>
      )}

      {/* Tier Selector Tabs */}
      <div className="flex flex-wrap gap-3" role="group" aria-label="Select voice stack tier">
        {PROFILE_TIERS.map((tier) => {
          const row = rows.find((r) => r.tier === tier);
          const active = selected === tier;
          const tierEnabled = row?.readiness?.enabled === true;
          const label = row?.label || DEFAULT_TIER_LABELS[tier];

          return (
            <button
              key={tier}
              type="button"
              disabled={busy}
              onClick={() => {
                setSelected(tier);
                setStatus("");
                setError("");
              }}
              className={`flex min-w-[200px] flex-col rounded-xl border p-3.5 text-left transition-all ${
                active
                  ? "border-accent-primary bg-accent-dim shadow-md"
                  : "border-surface-border bg-surface-card hover:border-surface-border-subtle hover:bg-surface-raised/40"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs uppercase tracking-wider text-text-subtle font-mono">{tier}</span>
                <span
                  className={`size-2 rounded-full ${
                    tierEnabled ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-neutral-600"
                  }`}
                />
              </div>
              <span className="mt-1 font-semibold text-sm text-text">{label}</span>
              <div className="mt-2 flex items-center gap-2">
                <span className={`text-[11px] font-medium ${tierEnabled ? "text-emerald-400" : "text-text-muted"}`}>
                  {tierEnabled ? "Active / Enabled" : "Disabled"}
                </span>
                {row?.retailRate?.inrPaisePerMin && (
                  <span className="font-mono text-[11px] text-text-subtle">
                    · ₹{(row.retailRate.inrPaisePerMin / 100).toFixed(2)}/min
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected Tier Management Panel */}
      <DevCard
        title={`${tierLabelInput || DEFAULT_TIER_LABELS[selected]} Configuration`}
        description="Select the provider and model for STT, LLM, and TTS. Changes apply to all new tenant calls in this tier."
      >
        {/* Tier Controls Bar (Name + Enable/Disable Toggle + Rate Info) */}
        <div className="rounded-xl border border-surface-border bg-surface-raised/50 p-4 mb-6">
          <div className="grid gap-4 md:grid-cols-3 items-center">
            {/* Custom Name */}
            <div>
              <label className="block text-xs font-medium text-text-muted mb-1.5">
                Tier Display Name (Visible to Tenants)
              </label>
              <input
                type="text"
                value={tierLabelInput}
                onChange={(e) => handleTierLabelChange(e.target.value)}
                placeholder={DEFAULT_TIER_LABELS[selected]}
                className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              />
            </div>

            {/* Enable/Disable Status & Toggle */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-muted">Tier Status for Tenants</span>
              <div className="flex items-center gap-3">
                <StatusPill tone={isEnabled ? "good" : "muted"}>
                  {isEnabled ? "Enabled for Tenants" : "Disabled (Hidden)"}
                </StatusPill>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleToggleActivation(!isEnabled)}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                    isEnabled
                      ? "border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
                      : "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                  }`}
                >
                  {isEnabled ? "Disable Tier" : "Enable Tier"}
                </button>
              </div>
            </div>

            {/* Duplicate Stack Button & Action */}
            <div className="flex flex-col gap-1.5 md:items-end">
              <span className="text-xs font-medium text-text-muted">Stack Replication</span>
              <button
                type="button"
                disabled={busy}
                onClick={handleOpenDuplicateModal}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text hover:border-surface-border-subtle hover:bg-surface-raised transition-colors shadow-sm"
              >
                <span>📋 Duplicate Stack</span>
              </button>
            </div>
          </div>
        </div>

        {/* 3 Pipeline Component Dropdowns */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* 1. Speech-to-Text (STT) */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-400">
                  1
                </span>
                <h3 className="text-sm font-semibold text-text">Speech-to-Text (STT)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Recognition</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  STT Provider
                </label>
                <select
                  value={draft.stt.provider}
                  onChange={(e) => handleSttProviderChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                >
                  {availableSttProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  STT Model
                </label>
                <select
                  value={draft.stt.model}
                  onChange={(e) => handleSttModelChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs"
                >
                  {currentSttModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              Low-latency streaming speech recognition configured for real-time PSTN telephony.
            </p>
          </div>

          {/* 2. Reasoning & Intelligence (LLM) */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-purple-500/20 text-xs font-bold text-purple-400">
                  2
                </span>
                <h3 className="text-sm font-semibold text-text">Intelligence (LLM)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Generation</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  LLM Provider
                </label>
                <select
                  value={draft.llm.provider}
                  onChange={(e) => handleLlmProviderChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                >
                  {availableLlmProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  LLM Model
                </label>
                <select
                  value={draft.llm.modelId}
                  onChange={(e) => handleLlmModelChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs"
                >
                  {currentLlmModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              Powers conversational reasoning, system instructions, and tool calling with streaming tokens.
            </p>
          </div>

          {/* 3. Speech Synthesis (TTS) */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500/20 text-xs font-bold text-emerald-400">
                  3
                </span>
                <h3 className="text-sm font-semibold text-text">Speech Output (TTS)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Synthesis</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  TTS Provider
                </label>
                <select
                  value={currentTtsProvider}
                  onChange={(e) => handleTtsProviderChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                >
                  {availableTtsProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  TTS Model
                </label>
                <select
                  value={currentTtsModel}
                  onChange={(e) => handleTtsModelChange(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs"
                >
                  {currentTtsModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Warning when chosen provider is missing setup/credits */}
            {(() => {
              const cat = providers.find((cp) => cp.id === currentTtsProvider);
              const hasWarning = cat && (!cat.enabled || !cat.configured);
              if (!hasWarning) return null;
              return (
                <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                  <span className="text-base leading-none">⚠️</span>
                  <div className="space-y-0.5">
                    <p className="font-semibold text-amber-100">
                      Warning: {currentTtsProvider.toUpperCase()} credits or API credentials not configured/active
                    </p>
                    <p className="text-[11px] text-amber-200/80">
                      The chosen stack will <strong>never silently fall back to any default provider</strong>. If credits or quota are exhausted, call synthesis will report an error for this provider. Ensure account balance is active.
                    </p>
                  </div>
                </div>
              );
            })()}

            <p className="text-[11px] text-text-subtle">
              Curated voice personas (Conversational & Promotional) are automatically bound to this speech engine. All speech options stream over low-latency WebSockets.
            </p>
          </div>
        </div>

        {/* Curated Voice Catalog Auto-Binding Notification & Audio Playback Preview */}
        <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <p className="text-xs font-semibold text-text">
                Active Speech Engine: {currentTtsProvider.toUpperCase()} ({currentTtsModel})
              </p>
              <p className="mt-0.5 text-xs text-text-muted">
                {currentTtsProvider === "sarvam"
                  ? "Curated Indian Regional personas enabled: Shubh, Priya, Pooja, Simran, Neha, Rahul."
                  : currentTtsProvider === "cartesia"
                  ? "Sonic ultra-low-latency multilingual voices: Voice 1 (Female), Voice 2 (Male)."
                  : currentTtsProvider === "gnani"
                  ? "Timbre expressive audio tag voices: Voice 1 (Female), Voice 2 (Male)."
                  : "Gemini conversational voices enabled: Zephyr, Puck, Aoede, Leda, Kore, Fenrir, Charon."}
              </p>
            </div>
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
              Curated Voices Linked
            </span>
          </div>

          {/* Voice Preview Playback Grid */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {currentVoices.map((v) => {
              const isPlaying = playingVoiceId === v.id;
              const isLoading = previewLoadingId === v.id;
              return (
                <div
                  key={v.id}
                  className={`flex items-center justify-between rounded-xl border p-3 transition-colors ${
                    isPlaying
                      ? "border-emerald-500/40 bg-emerald-500/10"
                      : "border-surface-border bg-surface-panel hover:bg-surface-raised/60"
                  }`}
                >
                  <div className="space-y-0.5 min-w-0 pr-2">
                    <p className="text-xs font-medium text-text truncate">{v.label}</p>
                    <p className="text-[10px] font-mono text-text-subtle truncate">
                      ID: {v.providerVoiceId}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={isLoading}
                    onClick={() => void handlePlayVoicePreview(v.id)}
                    className={`shrink-0 flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                      isPlaying
                        ? "bg-emerald-500 text-white shadow-sm"
                        : "bg-surface-raised text-text hover:bg-accent-primary hover:text-white"
                    }`}
                  >
                    {isLoading ? (
                      <span>Loading…</span>
                    ) : isPlaying ? (
                      <span>⏸ Stop</span>
                    ) : (
                      <span>▶ Play</span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Supported Languages */}
        <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4">
          <h4 className="text-xs font-semibold text-text mb-1">Supported Languages & Dialects</h4>
          <p className="text-xs text-text-muted mb-2">
            Languages verified for recognition, translation, and speech generation in this tier.
          </p>
          <div className="flex flex-wrap gap-2">
            {draft.supportedLanguages.map((lang) => (
              <span
                key={lang}
                className="rounded-lg border border-surface-border bg-surface-panel px-2.5 py-1 font-mono text-xs text-text"
              >
                {lang}
              </span>
            ))}
          </div>
        </div>

        {/* Blockers alert if any */}
        {blockers.length > 0 && (
          <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <h4 className="text-xs font-semibold text-amber-300 mb-2">Readiness Blockers ({blockers.length})</h4>
            <ul className="space-y-1 text-xs text-amber-200">
              {blockers.map((b, i) => (
                <li key={i}>• {b.message} ({b.code})</li>
              ))}
            </ul>
          </div>
        )}

        {/* Save & Apply Footer */}
        <div className="mt-6 pt-4 border-t border-border flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button
              type="button"
              disabled={busy}
              onClick={() => void handleSaveProfile()}
              className="px-5 py-2.5"
            >
              {busy ? "Saving Configuration…" : "Save Tier Configuration"}
            </Button>
            {dirty && (
              <span className="text-xs font-medium text-amber-400">
                ● Unsaved changes
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => {
                const def = defaultProfileForTier(selected);
                setDraft(def);
                setTierLabelInput(DEFAULT_TIER_LABELS[selected]);
                setDirty(true);
              }}
            >
              Load Recommended Default
            </Button>
          </div>
        </div>
      </DevCard>

      {/* Duplicate Stack Modal */}
      {showDuplicateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-semibold text-text">Duplicate Voice Stack</h3>
            <p className="text-xs text-text-muted">
              Duplicate all STT, LLM, and TTS models, WebSocket options, and voice configurations from{" "}
              <strong>{tierLabelInput || DEFAULT_TIER_LABELS[selected]}</strong> into a target tier.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">Target Tier</label>
                <select
                  value={duplicateTargetTier}
                  onChange={(e) => setDuplicateTargetTier(e.target.value as ProfileTier)}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                >
                  {PROFILE_TIERS.map((t) => (
                    <option key={t} value={t}>
                      {DEFAULT_TIER_LABELS[t]} ({t.toUpperCase()})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">Duplicated Stack Label</label>
                <input
                  type="text"
                  value={duplicateLabel}
                  onChange={(e) => setDuplicateLabel(e.target.value)}
                  placeholder="Custom Stack Name"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-surface-border-subtle">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setShowDuplicateModal(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={busy}
                onClick={() => void handleConfirmDuplicate()}
              >
                {busy ? "Duplicating…" : "Confirm Duplicate"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
