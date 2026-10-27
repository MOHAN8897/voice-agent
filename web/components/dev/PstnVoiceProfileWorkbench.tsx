"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type ProfileTier = string;

type StageProfile = { provider: string; model: string };
type LlmProfile = { provider: string; modelId: string; apiMode: string };
type VoiceProfile = {
  id: string;
  label: string;
  providerVoiceId: string;
  languages: string[];
  category?: string;
  gender?: string;
  tone?: string;
  selectable?: boolean;
  preferredLanguages?: string[];
  unavailableReason?: string;
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
type VoiceDynamics = {
  speed: number;
  pitch?: number;
  temperature?: number;
  emotion?: string;
  volume?: number;
};
type TtsKnobOption = { value: string; label: string };
type TtsKnobKey = "speed" | "pitch" | "temperature" | "emotion" | "volume";
type TtsKnobSpec = {
  key: TtsKnobKey;
  label: string;
  description?: string;
  kind: "range" | "select";
  min?: number;
  max?: number;
  step?: number;
  default?: number | string;
  unit?: string;
  native?: string;
  options?: TtsKnobOption[];
};
type ComposedProfile = {
  schemaVersion: 1;
  enabled: boolean;
  label?: string;
  retailRateInr?: number | null;
  webRetailRateInr?: number | null;
  supplierCostInr?: number | null;
  supportedLanguages: string[];
  stt: StageProfile;
  llm: LlmProfile;
  engines: EngineProfile[];
  evidence: ProfileEvidence;
  voiceDynamics?: VoiceDynamics;
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
  webRetailRate?: RetailRate;
  readOnly?: boolean;
};
type ProfilesResponse = { environment: string; profiles: TierProfileRow[] };
type CatalogModel = { id: string; label?: string; realtime?: boolean; api_mode?: string; api_modes?: string[]; voices?: VoiceProfile[]; knobs?: TtsKnobSpec[] };
type CatalogProvider = { id: string; label?: string; enabled?: boolean; configured?: boolean; models?: { stt?: CatalogModel[]; llm?: CatalogModel[]; tts?: CatalogModel[] } };
type CatalogResponse = { providers?: CatalogProvider[]; voiceInventory?: { errors?: string[] } };

type TelephonyProvider = {
  id: string;
  name?: string;
  enabled?: boolean;
  ready?: boolean;
  phone_number?: string;
  connection_id?: string;
  account_info?: { auth_id?: string; app_id?: string };
};
type TelephonyStatus = {
  active_provider?: string;
  active_enabled?: boolean;
  active_ready?: boolean;
  providers?: TelephonyProvider[];
  enabled_providers?: string[];
};

const DEFAULT_TIER_LABELS: Record<string, string> = {
  low: "Economical Tier",
  medium: "Standard Regional Tier",
  premium: "Gemini 3.8 Live (Flagship)",
};

function getVoicesForTtsProvider(providers: CatalogProvider[], provider: string, model: string, languages: string[], previous: VoiceProfile[] = []): VoiceProfile[] {
  const rows = providers.find((entry) => entry.id === provider)?.models?.tts?.find((entry) => entry.id === model)?.voices || [];
  return rows.filter((voice) => voice.selectable !== false).map((voice) => ({ ...voice,
    id: previous.find((item) => item.providerVoiceId === voice.providerVoiceId)?.id || voice.id,
    languages: voice.languages.filter((language) => !languages.length || languages.includes(language)),
  })).filter((voice) => voice.languages.length > 0);
}

const DEFAULT_VOICE_DYNAMICS: VoiceDynamics = { speed: 1.0, pitch: 0.0, temperature: 0.7, emotion: "calm", volume: 1.0 };

// Native live voice (Gemini Live / OpenAI Realtime) exposes one delivery knob:
// speed, clamped by server/realtime/models.normalize_realtime_speed.
const NATIVE_LIVE_KNOBS: TtsKnobSpec[] = [
  {
    key: "speed",
    label: "Live Voice Pace",
    description: "Applied to the native realtime voice instruction; no separate TTS engine is used.",
    kind: "range",
    min: 0.25,
    max: 1.5,
    step: 0.05,
    default: 1.0,
    native: "speed",
    unit: "x",
  },
];

const FALLBACK_SPEED_KNOB: TtsKnobSpec = {
  key: "speed",
  label: "Speaking Pace",
  description: "Speech engine pace.",
  kind: "range",
  min: 0.25,
  max: 2.0,
  step: 0.05,
  default: 1.0,
  native: "pace",
  unit: "x",
};

function resolveModelKnobs(providers: CatalogProvider[], provider: string, model: string): TtsKnobSpec[] | null {
  const specs = providers.find((entry) => entry.id === provider)?.models?.tts?.find((entry) => entry.id === model)?.knobs;
  return Array.isArray(specs) && specs.length > 0 ? specs : null;
}

function dynamicsValue(dynamics: VoiceDynamics | undefined, key: TtsKnobKey): number | string | undefined {
  if (!dynamics) return undefined;
  switch (key) {
    case "speed": return dynamics.speed;
    case "pitch": return dynamics.pitch;
    case "temperature": return dynamics.temperature;
    case "emotion": return dynamics.emotion;
    case "volume": return dynamics.volume;
  }
}

function knobPatch(key: TtsKnobKey, value: number | string): Partial<VoiceDynamics> {
  switch (key) {
    case "speed": return { speed: Number(value) };
    case "pitch": return { pitch: Number(value) };
    case "temperature": return { temperature: Number(value) };
    case "emotion": return { emotion: String(value) };
    case "volume": return { volume: Number(value) };
  }
}

function assignKnob(target: VoiceDynamics, key: TtsKnobKey, value: number | string): void {
  switch (key) {
    case "speed": target.speed = Number(value); break;
    case "pitch": target.pitch = Number(value); break;
    case "temperature": target.temperature = Number(value); break;
    case "emotion": target.emotion = String(value); break;
    case "volume": target.volume = Number(value); break;
  }
}

function normalizeDynamicsForKnobs(dynamics: VoiceDynamics | undefined, knobs: TtsKnobSpec[]): VoiceDynamics {
  const next: VoiceDynamics = { speed: 1.0 };
  const speedSpec = knobs.find((spec) => spec.key === "speed");
  const rawSpeed = Number(dynamics?.speed ?? speedSpec?.default ?? 1.0);
  const speedMin = Number(speedSpec?.min ?? FALLBACK_SPEED_KNOB.min);
  const speedMax = Number(speedSpec?.max ?? FALLBACK_SPEED_KNOB.max);
  next.speed = Math.max(speedMin, Math.min(speedMax, Number.isFinite(rawSpeed) ? rawSpeed : 1.0));
  for (const spec of knobs) {
    if (spec.key === "speed") continue;
    if (spec.kind === "select") {
      const allowed = (spec.options || []).map((option) => option.value);
      const current = String(dynamicsValue(dynamics, spec.key) ?? spec.default ?? "");
      if (allowed.includes(current)) assignKnob(next, spec.key, current);
      continue;
    }
    const raw = dynamicsValue(dynamics, spec.key);
    if (raw === undefined || raw === null || raw === "") continue;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) continue;
    assignKnob(next, spec.key, Math.max(Number(spec.min), Math.min(Number(spec.max), parsed)));
  }
  return next;
}

function speedPresetsFor(spec: TtsKnobSpec): Array<{ value: number; label: string }> {
  const min = Number(spec.min);
  const max = Number(spec.max);
  const candidates = [
    { value: 0.9, label: "Patient" },
    { value: 1.0, label: "Standard" },
    { value: 1.1, label: "Dynamic" },
    { value: 1.25, label: "Energetic" },
  ].filter((preset) => preset.value >= min && preset.value <= max);
  return candidates.length > 0 ? candidates : [{ value: Math.max(min, Math.min(max, 1.0)), label: "Standard" }];
}

const EMPTY_EVIDENCE: ProfileEvidence = {
  sarvamModelAccess: false, sttVerified: false, ttsCatalogVerified: false,
  toolsVerified: false, capacityVerified: false, mediaFormatsVerified: false, credentialRefConfigured: false,
};

function defaultProfileForTier(tier: ProfileTier): ComposedProfile {
  if (tier === "premium") {
    return {
      schemaVersion: 1,
      enabled: false,
      label: DEFAULT_TIER_LABELS[tier] || "Gemini 3.8 Live (Flagship)",
      retailRateInr: 10.0,
      supplierCostInr: 3.5,
      supportedLanguages: [
        "te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN",
        "bn-IN", "gu-IN", "pa-IN", "en-IN",
      ],
      stt: { provider: "gemini", model: "gemini-3.8-live-audio" },
      llm: { provider: "gemini", modelId: "gemini-2.5-flash", apiMode: "websocket" },
      engines: [
        {
          id: "gemini",
          label: "Gemini Live Native Audio",
          models: [
            {
              id: "gemini-3.8-live-tts",
              label: "Gemini 3.8 Live",
              provider: "gemini",
              model: "gemini-2.5-flash",
              apiMode: "websocket",
              voices: [
                { id: "Puck", providerVoiceId: "Puck", label: "Puck", languages: ["te-IN", "hi-IN", "en-IN"] },
                { id: "Charon", providerVoiceId: "Charon", label: "Charon", languages: ["te-IN", "hi-IN", "en-IN"] },
                { id: "Aoede", providerVoiceId: "Aoede", label: "Aoede", languages: ["te-IN", "hi-IN", "en-IN"] },
                { id: "Fenrir", providerVoiceId: "Fenrir", label: "Fenrir", languages: ["te-IN", "hi-IN", "en-IN"] },
                { id: "Kore", providerVoiceId: "Kore", label: "Kore", languages: ["te-IN", "hi-IN", "en-IN"] },
              ],
            },
          ],
        },
      ],
      evidence: { ...EMPTY_EVIDENCE },
      voiceDynamics: { ...DEFAULT_VOICE_DYNAMICS },
    };
  }
  const defaultSupplier = tier === "low" ? 1.2 : tier === "medium" ? 2.0 : 1.5;
  const defaultRetail = tier === "low" ? 3.5 : tier === "medium" ? 5.0 : 6.0;
  return {
    schemaVersion: 1,
    enabled: false,
    label: DEFAULT_TIER_LABELS[tier] || tier,
    retailRateInr: defaultRetail,
    supplierCostInr: defaultSupplier,
    supportedLanguages: [
      "te-IN", "hi-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN",
      "bn-IN", "gu-IN", "pa-IN", "en-IN",
    ],
    stt: { provider: "sarvam", model: "saaras:v3-realtime" },
    llm: { provider: "sarvam", modelId: "sarvam-105b-conversations", apiMode: "chat_completions_v1" },
    engines: [],
    evidence: { ...EMPTY_EVIDENCE },
    voiceDynamics: { ...DEFAULT_VOICE_DYNAMICS },
  };
}

function normalizeProfile(profile: ComposedProfile | null | undefined, tier: ProfileTier): ComposedProfile {
  const fallback = defaultProfileForTier(tier);
  if (!profile) return fallback;
  return {
    schemaVersion: 1,
    enabled: profile.enabled === true,
    label: profile.label || DEFAULT_TIER_LABELS[tier] || tier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    webRetailRateInr: profile.webRetailRateInr ?? null,
    retailRateInr: profile.retailRateInr !== undefined && profile.retailRateInr !== null ? Number(profile.retailRateInr) : (fallback.retailRateInr ?? null),
    supplierCostInr: profile.supplierCostInr !== undefined && profile.supplierCostInr !== null ? Number(profile.supplierCostInr) : (fallback.supplierCostInr ?? null),
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
    voiceDynamics: profile.voiceDynamics
      ? {
          speed: Number(profile.voiceDynamics.speed ?? 1.0),
          pitch: Number(profile.voiceDynamics.pitch ?? 0.0),
          temperature: Number(profile.voiceDynamics.temperature ?? 0.7),
          emotion: String(profile.voiceDynamics.emotion || DEFAULT_VOICE_DYNAMICS.emotion),
          volume: Number(profile.voiceDynamics.volume ?? 1.0),
        }
      : { ...DEFAULT_VOICE_DYNAMICS },
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
  if (typeof payload === "object" && payload !== null) {
    const raw = payload as Record<string, unknown>;
    const detail = raw.detail ?? raw.error ?? raw;
    if (typeof detail === "string" && detail.length < 300) return detail;
    if (typeof detail === "object" && detail !== null) {
      const d = detail as Record<string, unknown>;
      const err = (typeof d.error === "object" && d.error !== null) ? (d.error as Record<string, unknown>) : d;
      const message = typeof err.message === "string" ? err.message : typeof err.detail === "string" ? err.detail : "";
      const blockers = Array.isArray(err.blockers)
        ? err.blockers.map((b: any) => (typeof b === "object" && b !== null ? (b.message || b.code) : String(b))).filter(Boolean)
        : (typeof err.readiness === "object" && err.readiness !== null && Array.isArray((err.readiness as any).blockers))
        ? (err.readiness as any).blockers.map((b: any) => (typeof b === "object" && b !== null ? (b.message || b.code) : String(b))).filter(Boolean)
        : [];
      const blockerStr = blockers.length > 0 ? blockers.join("; ") : "";
      const revNote = typeof err.currentRevision === "number" ? ` (server revision is ${err.currentRevision})` : "";
      if (message && blockerStr) return `${message}: ${blockerStr}${revNote}`;
      if (message) return `${message}${revNote}`;
      if (blockerStr) return `${blockerStr}${revNote}`;
    }
  }
  return `Request failed (${response.status}).`;
}

const PROFILE_SECTIONS = [
  { id: "stack", label: "Voice Stack" },
  { id: "pricing", label: "Pricing" },
  { id: "telephony", label: "Telephony" },
  { id: "transcription", label: "Transcription" },
] as const;

type ProfileSectionId = (typeof PROFILE_SECTIONS)[number]["id"];

export function PstnVoiceProfileWorkbench() {
  const [rows, setRows] = useState<TierProfileRow[]>([]);
  const [activeSection, setActiveSection] = useState<ProfileSectionId>("stack");
  const [environment, setEnvironment] = useState("");
  const [selected, setSelected] = useState<ProfileTier>("low");
  const [draft, setDraft] = useState<ComposedProfile>(defaultProfileForTier("low"));
  const [tierLabelInput, setTierLabelInput] = useState<string>("");
  const [retailRateInput, setRetailRateInput] = useState<string>("");
  const [supplierCostInput, setSupplierCostInput] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [verification, setVerification] = useState<Record<string, { passed: boolean; detail: string }> | null>(null);
  const [providers, setProviders] = useState<CatalogProvider[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogRefreshing, setCatalogRefreshing] = useState(false);
  const [voiceCategory, setVoiceCategory] = useState("");
  const [autoSaveStatus, setAutoSaveStatus] = useState<string>("");
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const draftsByTierRef = useRef<Record<string, ComposedProfile>>({});
  const retailInputsByTierRef = useRef<Record<string, string>>({});
  const supplierInputsByTierRef = useRef<Record<string, string>>({});
  const labelsByTierRef = useRef<Record<string, string>>({});
  const pendingSaveRef = useRef<{ draft: ComposedProfile; label?: string; tier: ProfileTier } | null>(null);
  const activeTierRef = useRef<ProfileTier>("low");
  activeTierRef.current = selected;

  // Audio preview playback state
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Speed Dynamics Testing & Audition state
  const [testText, setTestText] = useState("నమస్కారం! నేను మీ రియల్ ఎస్టేట్ సేల్స్ అసిస్టెంట్ మోహన్‌ని. మీకు ఎలా సహాయపడగలను?");
  const [testVoiceId, setTestVoiceId] = useState("");
  const [isTestingDynamics, setIsTestingDynamics] = useState(false);
  const [isPlayingDynamics, setIsPlayingDynamics] = useState(false);
  const dynamicsAudioRef = useRef<HTMLAudioElement | null>(null);

  // Stack duplication state
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [duplicateNewSlug, setDuplicateNewSlug] = useState("");
  const [duplicateLabel, setDuplicateLabel] = useState("");

  // Platform & Channel Prices (INR) state
  const [pricesSaving, setPricesSaving] = useState(false);
  const [pricesStatus, setPricesStatus] = useState("");
  const [pricesError, setPricesError] = useState("");
  const [webInr, setWebInr] = useState("0");
  const [numberInr, setNumberInr] = useState("0");
  const [fxRate, setFxRate] = useState("95.64");
  const [liveFx, setLiveFx] = useState<number | null>(null);

  // Telephony Trunk State
  const [telephony, setTelephony] = useState<TelephonyStatus | null>(null);
  const [telephonyBusy, setTelephonyBusy] = useState(false);
  const [telephonyMsg, setTelephonyMsg] = useState("");
  const [telephonyError, setTelephonyError] = useState("");

  // Transcription Configuration State
  const [transcriptionMode, setTranscriptionMode] = useState<"off" | "live" | "post_call">("off");
  const [transcriptionLiveModel, setTranscriptionLiveModel] = useState("gpt-4o-mini-transcribe");
  const [saasPhoneRaw, setSaasPhoneRaw] = useState<Record<string, unknown> | null>(null);
  const [transcriptionSaving, setTranscriptionSaving] = useState(false);

  // Global Prewarm Greeting Synthesis Toggle State
  const [prewarmGreetingEnabled, setPrewarmGreetingEnabled] = useState<boolean>(true);
  const [prewarmLoading, setPrewarmLoading] = useState<boolean>(false);
  const [transcriptionStatus, setTranscriptionStatus] = useState("");
  const [transcriptionError, setTranscriptionError] = useState("");

  const selectedRow = rows.find((r) => r.tier === selected);
  const isEnabled = selectedRow?.readiness.enabled === true;
  const blockers = selectedRow?.readiness.blockers ?? [];

  const allDisplayTiers = useMemo(() => {
    const list: string[] = ["low", "medium", "premium"];
    rows.forEach((r) => {
      if (!list.includes(r.tier)) {
        list.push(r.tier);
      }
    });
    return list;
  }, [rows]);

  const loadCatalog = useCallback(async (refreshVoices = false) => {
    setCatalogRefreshing(true);
    try {
      const response = await portalFetch("dev", `/api/dev/stack/catalog${refreshVoices ? "?refreshVoices=true" : ""}`);
      if (!response.ok) throw new Error("The provider catalog could not be loaded.");
      const payload: CatalogResponse = await response.json();
      if (Array.isArray(payload.providers)) {
        setProviders(payload.providers);
        setCatalogError(payload.voiceInventory?.errors?.join(" ") || "");
      }
    } catch {
      setCatalogError("The provider catalog could not be loaded. Refresh before changing a stack.");
    } finally {
      setCatalogRefreshing(false);
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

  const loadPrices = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/admin/billing-rates");
      if (!res.ok) return;
      const data = await res.json();
      const r = data.rates;
      if (r) {
        setWebInr(String(r.webInrPerMin ?? (r.webUsdPerMin ? (r.webUsdPerMin * (r.fxRateInr || 95.64)).toFixed(2) : "0")));
        setNumberInr(String(r.numberMonthlyInr ?? (r.numberMonthlyUsd ? (r.numberMonthlyUsd * (r.fxRateInr || 95.64)).toFixed(2) : "0")));
        setFxRate(String(r.fxRateInr ?? "95.64"));
      }
      if (data.fx?.liveRateInr) {
        setLiveFx(data.fx.liveRateInr);
      }
    } catch {
      // Non-blocking prices fetch
    }
  }, []);

  const loadTelephony = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/telephony/status");
      if (!res.ok) return;
      const data = await res.json();
      setTelephony(data);
    } catch {
      // Non-blocking telephony fetch
    }
  }, []);

  const loadTranscription = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/stack/saas-phone");
      if (!res.ok) return;
      const data = await res.json();
      const saved = (data.saved?.stack_override || data.resolved) as Record<string, unknown> | undefined;
      if (saved) {
        setSaasPhoneRaw(saved);
        if (typeof saved.transcription_mode === "string") {
          setTranscriptionMode(saved.transcription_mode as "off" | "live" | "post_call");
        }
        if (typeof saved.transcription_live_model === "string") {
          setTranscriptionLiveModel(saved.transcription_live_model);
        }
      }
    } catch {
      // Non-blocking transcription fetch
    }
  }, []);

  const loadPrewarmGreeting = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/stack/prewarm-greeting");
      if (!res.ok) return;
      const data = await res.json();
      if (typeof data.enabled === "boolean") {
        setPrewarmGreetingEnabled(data.enabled);
      }
    } catch {
      // Non-blocking prewarm greeting fetch
    }
  }, []);

  const togglePrewarmGreeting = async (nextState: boolean) => {
    setPrewarmLoading(true);
    try {
      const res = await portalFetch("dev", "/api/dev/stack/prewarm-greeting", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextState }),
      });
      if (res.ok) {
        setPrewarmGreetingEnabled(nextState);
      }
    } catch {
      // Non-blocking error handling
    } finally {
      setPrewarmLoading(false);
    }
  };

  useEffect(() => {
    void loadProfiles();
    void loadCatalog();
    void loadPrices();
    void loadTelephony();
    void loadTranscription();
    void loadPrewarmGreeting();
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, [loadProfiles, loadCatalog, loadPrices, loadTelephony, loadTranscription, loadPrewarmGreeting]);

  useEffect(() => {
    const row = rows.find((r) => r.tier === selected);
    // Do not cache an empty startup draft ahead of the saved profile response.
    if (!row && loading) return;
    const activeRefDraft = draftsByTierRef.current[selected];
    const norm = activeRefDraft || normalizeProfile(row?.composedProfile, selected);
    if ((norm.retailRateInr === null || norm.retailRateInr === undefined) && row?.retailRate?.inrPaisePerMin) {
      norm.retailRateInr = Number((row.retailRate.inrPaisePerMin / 100).toFixed(2));
    }
    setDraft(norm);
    draftsByTierRef.current[selected] = norm;

    const labelVal = labelsByTierRef.current[selected] ?? (row?.label || norm.label || DEFAULT_TIER_LABELS[selected] || selected);
    setTierLabelInput(labelVal);
    labelsByTierRef.current[selected] = labelVal;

    const retailVal = retailInputsByTierRef.current[selected] ?? (norm.retailRateInr !== null && norm.retailRateInr !== undefined ? String(norm.retailRateInr) : "");
    setRetailRateInput(retailVal);
    retailInputsByTierRef.current[selected] = retailVal;

    const supplierVal = supplierInputsByTierRef.current[selected] ?? (norm.supplierCostInr !== null && norm.supplierCostInr !== undefined ? String(norm.supplierCostInr) : "");
    setSupplierCostInput(supplierVal);
    supplierInputsByTierRef.current[selected] = supplierVal;

    setDirty(false);
  }, [rows, selected, loading]);

  // STT Options
  const availableSttProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.stt?.length || 0) > 0).map((p) => {
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
    return [];
  }, [providers, draft.stt.provider]);

  // LLM Options
  const availableLlmProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.llm?.length || 0) > 0).map((p) => {
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
    return [];
  }, [providers, draft.llm.provider]);

  // TTS Options
  const currentTtsModelObj = draft.engines[0]?.models[0];
  const currentTtsProvider = currentTtsModelObj?.provider || "";
  const currentTtsModel = currentTtsModelObj?.model || "";

  const availableTtsProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.tts?.length || 0) > 0).map((p) => {
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
    return [];
  }, [providers, currentTtsProvider]);

  // Native realtime voice (Gemini Live / OpenAI Realtime) bypasses the composed
  // TTS engine, so only the live voice pace knob applies.
  const isNativeRealtimeLlm = draft.llm.apiMode === "websocket";
  const currentTtsKnobs = useMemo(() => {
    if (isNativeRealtimeLlm) return NATIVE_LIVE_KNOBS;
    return resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB];
  }, [providers, currentTtsProvider, currentTtsModel, isNativeRealtimeLlm]);
  const speedKnob = currentTtsKnobs.find((spec) => spec.key === "speed") || FALLBACK_SPEED_KNOB;
  const secondaryKnobs = currentTtsKnobs.filter((spec) => spec.key !== "speed");

  async function executeSaveProfile(targetDraft?: ComposedProfile, customLabel?: string, targetTier?: ProfileTier) {
    const tierToSave = targetTier || selected;
    const activeDraft = targetDraft || draftsByTierRef.current[tierToSave] || draft;
    const currentLabelInput = labelsByTierRef.current[tierToSave] ?? tierLabelInput;
    const labelVal = (customLabel !== undefined ? customLabel : currentLabelInput).trim() || DEFAULT_TIER_LABELS[tierToSave] || tierToSave;
    const isNativeLive = activeDraft.llm.apiMode === "websocket" || tierToSave === "premium";

    const ttsProv = activeDraft.engines[0]?.models[0]?.provider || (isNativeLive ? "gemini" : currentTtsProvider);
    const ttsMdl = activeDraft.engines[0]?.models[0]?.model || (isNativeLive ? "gemini-2.5-flash" : currentTtsModel);
    const matchedTtsModel = providers.find((entry) => entry.id === ttsProv)?.models?.tts?.find((entry) => entry.id === ttsMdl);
    const languages = activeDraft.supportedLanguages.length > 0
      ? activeDraft.supportedLanguages
      : [...new Set((matchedTtsModel?.voices || []).flatMap((voice) => voice.languages))];
    let voices = getVoicesForTtsProvider(providers, ttsProv, ttsMdl, languages, activeDraft.engines[0]?.models[0]?.voices);
    if (!voices.length && isNativeLive) {
      voices = defaultProfileForTier("premium").engines[0]?.models[0]?.voices || [];
    }
    const targetKnobs = isNativeLive
      ? NATIVE_LIVE_KNOBS
      : resolveModelKnobs(providers, ttsProv, ttsMdl);

    if (!isNativeLive && (!activeDraft.stt.model || !activeDraft.stt.provider)) {
      setError("Choose a speech recognition (STT) model for this tier.");
      setDirty(true);
      return;
    }
    if (!activeDraft.llm.modelId) {
      setError("Choose an intelligence (LLM) model.");
      setDirty(true);
      return;
    }
    if (!voices.length) {
      setError("Choose a complete stack with voices from the current provider catalog.");
      setDirty(true);
      return;
    }

    const currentRetailStr = retailInputsByTierRef.current[tierToSave] ?? retailRateInput;
    const currentSupplierStr = supplierInputsByTierRef.current[tierToSave] ?? supplierCostInput;

    const parsedRetail = activeDraft.retailRateInr !== undefined && activeDraft.retailRateInr !== null
      ? activeDraft.retailRateInr
      : (currentRetailStr.trim() !== "" && !isNaN(parseFloat(currentRetailStr)) ? parseFloat(currentRetailStr) : null);
    const parsedSupplier = activeDraft.supplierCostInr !== undefined && activeDraft.supplierCostInr !== null
      ? activeDraft.supplierCostInr
      : (currentSupplierStr.trim() !== "" && !isNaN(parseFloat(currentSupplierStr)) ? parseFloat(currentSupplierStr) : null);

    const targetRow = rows.find((r) => r.tier === tierToSave);
    const tierEnabled = targetRow?.readiness?.enabled === true;

    const payload: ComposedProfile = {
      schemaVersion: 1,
      enabled: tierEnabled,
      label: labelVal,
      webRetailRateInr: activeDraft.webRetailRateInr ?? null,
      retailRateInr: parsedRetail !== null && !isNaN(parsedRetail) ? parsedRetail : null,
      supplierCostInr: parsedSupplier !== null && !isNaN(parsedSupplier) ? parsedSupplier : null,
      supportedLanguages: languages.length > 0 ? languages : ["te-IN", "hi-IN", "en-IN"],
      stt: {
        provider: activeDraft.stt.provider || (isNativeLive ? "gemini" : "sarvam"),
        model: activeDraft.stt.model || (isNativeLive ? "gemini-3.8-live-audio" : "saaras:v3-realtime"),
      },
      llm: {
        provider: activeDraft.llm.provider || (isNativeLive ? "gemini" : "sarvam"),
        modelId: activeDraft.llm.modelId || (isNativeLive ? "gemini-2.5-flash" : "sarvam-105b-conversations"),
        apiMode: activeDraft.llm.apiMode || (isNativeLive ? "websocket" : "chat_completions_v1"),
      },
      engines: [
        {
          id: activeDraft.engines[0]?.id || ttsProv,
          label: ttsProv === "sarvam" ? "Sarvam Bulbul" : ttsProv === "gemini" ? (isNativeLive ? "Gemini Live Native Audio" : "Gemini TTS") : ttsProv === "cartesia" ? "Cartesia Sonic" : "Gnani.ai Timbre",
          models: [
            {
              id: activeDraft.engines[0]?.models[0]?.id || ttsMdl,
              label: ttsMdl,
              provider: ttsProv,
              model: ttsMdl,
              apiMode: activeDraft.engines[0]?.models[0]?.apiMode || matchedTtsModel?.api_mode || (isNativeLive ? "websocket" : ""),
              voices,
            },
            ...(activeDraft.engines[0]?.models.slice(1) || []),
          ],
        },
        ...activeDraft.engines.slice(1),
      ],
      evidence: { ...activeDraft.evidence },
      voiceDynamics: targetKnobs
        ? normalizeDynamicsForKnobs(activeDraft.voiceDynamics, targetKnobs)
        : (activeDraft.voiceDynamics || { ...DEFAULT_VOICE_DYNAMICS }),
    };

    const expectedRev = targetRow?.profileRevision !== null && targetRow?.profileRevision !== undefined
      ? targetRow.profileRevision
      : 0;

    setAutoSaveStatus("⚡ Auto-saving changes…");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${tierToSave}`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: expectedRev,
          composedProfile: payload,
        }),
      });

      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      draftsByTierRef.current[tierToSave] = payload;
      pendingSaveRef.current = null;
      await loadProfiles(false);
      await loadPrices();
      setAutoSaveStatus("✓ Auto-saved & applied globally");
      setDirty(false);
      setTimeout(() => setAutoSaveStatus(""), 3500);
    } catch (caught) {
      setAutoSaveStatus("⚠️ Save error");
      setError(caught instanceof Error ? caught.message : "Could not save tier configuration.");
      void loadProfiles(false);
    }
  }

  function triggerAutoSave(nextDraft: ComposedProfile, customLabel?: string, delayMs: number = 0, targetTier?: ProfileTier) {
    const tierToSave = targetTier || selected;
    pendingSaveRef.current = { draft: nextDraft, label: customLabel, tier: tierToSave };
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    if (delayMs > 0) {
      setAutoSaveStatus("Typing…");
      autoSaveTimerRef.current = setTimeout(() => {
        autoSaveTimerRef.current = null;
        pendingSaveRef.current = null;
        void executeSaveProfile(nextDraft, customLabel, tierToSave);
      }, delayMs);
    } else {
      pendingSaveRef.current = null;
      void executeSaveProfile(nextDraft, customLabel, tierToSave);
    }
  }

  function switchSelectedTier(newTier: ProfileTier) {
    if (newTier === selected) return;
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    if (pendingSaveRef.current) {
      const { draft: pDraft, label: pLabel, tier: pTier } = pendingSaveRef.current;
      pendingSaveRef.current = null;
      void executeSaveProfile(pDraft, pLabel, pTier);
    }
    setStatus("");
    setError("");
    setSelected(newTier);
  }

  function handleSttProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.stt || [];
    const firstModel = models[0]?.id;
    if (!firstModel) return;
    const nextDraft = {
      ...draft,
      stt: { provider, model: firstModel },
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleSttModelChange(model: string) {
    const nextDraft = {
      ...draft,
      stt: { ...draft.stt, model },
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleLlmProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.llm || [];
    const first = models[0];
    if (!first) return;
    const nextKnobs = first.api_mode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB]);
    const nextDraft = {
      ...draft,
      llm: { provider, modelId: first.id, apiMode: first.api_mode || "" },
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleLlmModelChange(modelId: string) {
    const matched = currentLlmModels.find((m) => m.id === modelId);
    const apiMode = matched?.apiMode || "chat_completions_v1";
    const nextKnobs = apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB]);
    const nextDraft = {
      ...draft,
      llm: { ...draft.llm, modelId, apiMode },
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleTtsProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.tts || [];
    const first = models[0];
    if (!first) return;
    const languages = draft.supportedLanguages;
    const voices = getVoicesForTtsProvider(providers, provider, first.id, []);
    const nextKnobs = draft.llm.apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, provider, first.id) || [FALLBACK_SPEED_KNOB]);

    const nextDraft: ComposedProfile = {
      ...draft,
      supportedLanguages: [...new Set(voices.flatMap((voice) => voice.languages))],
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
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
              apiMode: first.api_mode || "",
              voices,
            },
          ],
        },
      ],
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleTtsModelChange(model: string) {
    const matched = currentTtsModels.find((m) => m.id === model);
    const languages = draft.supportedLanguages;
    const voices = getVoicesForTtsProvider(providers, currentTtsProvider, model, []);
    const nextKnobs = draft.llm.apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, model) || [FALLBACK_SPEED_KNOB]);

    const engines = [...draft.engines];
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
    const nextDraft: ComposedProfile = {
      ...draft,
      supportedLanguages: [...new Set(voices.flatMap((voice) => voice.languages))],
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
      engines: [engine],
    };
    setDraft(nextDraft);
    setDirty(false);
    triggerAutoSave(nextDraft);
  }

  function handleTierLabelChange(val: string) {
    setTierLabelInput(val);
    labelsByTierRef.current[selected] = val;
    const nextDraft = { ...draft, label: val };
    setDraft(nextDraft);
    draftsByTierRef.current[selected] = nextDraft;
    triggerAutoSave(nextDraft, val, 700, selected);
  }

  function handleRetailRateChange(val: string) {
    setRetailRateInput(val);
    retailInputsByTierRef.current[selected] = val;
    const num = parseFloat(val);
    const nextDraft = { ...draft, retailRateInr: !isNaN(num) ? num : null };
    setDraft(nextDraft);
    draftsByTierRef.current[selected] = nextDraft;
    triggerAutoSave(nextDraft, undefined, 800, selected);
  }

  function handleSupplierCostChange(val: string) {
    setSupplierCostInput(val);
    supplierInputsByTierRef.current[selected] = val;
    const num = parseFloat(val);
    const nextDraft = { ...draft, supplierCostInr: !isNaN(num) ? num : null };
    setDraft(nextDraft);
    draftsByTierRef.current[selected] = nextDraft;
    triggerAutoSave(nextDraft, undefined, 800, selected);
  }

  function handleWebRateChange(val: string) {
    const value = val === "" ? null : Number(val);
    const nextDraft = { ...draft, webRetailRateInr: value };
    setDraft(nextDraft);
    draftsByTierRef.current[selected] = nextDraft;
    if (value !== null && (!Number.isFinite(value) || value <= 0)) {
      setDirty(true); setError("Web call price must be positive."); return;
    }
    triggerAutoSave(nextDraft, undefined, 800, selected);
  }

  function handleDynamicsChange(patch: Partial<VoiceDynamics>) {
    const merged: VoiceDynamics = {
      speed: draft.voiceDynamics?.speed ?? 1.0,
      pitch: draft.voiceDynamics?.pitch,
      temperature: draft.voiceDynamics?.temperature,
      emotion: draft.voiceDynamics?.emotion,
      volume: draft.voiceDynamics?.volume,
      ...patch,
    };
    const nextDraft: ComposedProfile = {
      ...draft,
      voiceDynamics: normalizeDynamicsForKnobs(merged, currentTtsKnobs),
    };
    setDraft(nextDraft);
    triggerAutoSave(nextDraft, undefined, 400);
  }

  async function handleTestSpeedDynamics() {
    if (isPlayingDynamics && dynamicsAudioRef.current) {
      dynamicsAudioRef.current.pause();
      dynamicsAudioRef.current = null;
      setIsPlayingDynamics(false);
      return;
    }
    if (dynamicsAudioRef.current) {
      dynamicsAudioRef.current.pause();
      dynamicsAudioRef.current = null;
    }
    setIsTestingDynamics(true);
    setError("");
    try {
      const activeVoice = currentVoices.find((voice) => voice.id === testVoiceId) || currentVoices[0];
      if (!activeVoice) throw new Error("Choose a verified voice first.");
      const dyn = normalizeDynamicsForKnobs(draft.voiceDynamics || DEFAULT_VOICE_DYNAMICS, currentTtsKnobs);
      const response = await portalFetch("dev", "/api/dev/stack/voice-preview", {
        method: "POST",
        body: JSON.stringify({
          provider: currentTtsProvider,
          model: currentTtsModel,
          voiceId: activeVoice.providerVoiceId,
          text: testText,
          language: activeVoice.languages[0],
          speed: dyn.speed,
          pitch: dyn.pitch,
          temperature: dyn.temperature,
          emotion: dyn.emotion,
          volume: dyn.volume,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const b64 = data.audio_base64;
      if (!b64) throw new Error("No audition audio returned by server.");
      const audio = new Audio(`data:audio/wav;base64,${b64}`);
      dynamicsAudioRef.current = audio;
      audio.onended = () => {
        setIsPlayingDynamics(false);
        dynamicsAudioRef.current = null;
      };
      audio.onerror = () => {
        setIsPlayingDynamics(false);
        dynamicsAudioRef.current = null;
      };
      await audio.play();
      setIsPlayingDynamics(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate speed dynamics preview.");
    } finally {
      setIsTestingDynamics(false);
    }
  }

  async function handleDeleteTier(tierToDelete: string) {
    if (["low", "medium", "premium"].includes(tierToDelete)) {
      setError("Core tiers (Economical, Standard, and Flagship) cannot be deleted.");
      return;
    }
    const tierRow = rows.find((r) => r.tier === tierToDelete);
    const label = tierRow?.label || tierToDelete;
    if (!window.confirm(`Are you sure you want to delete the tier "${label}" (${tierToDelete})? This will permanently remove it from the platform.`)) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${tierToDelete}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await responseError(response));
      await loadProfiles(false);
      switchSelectedTier("medium");
      setStatus(`Tier "${label}" (${tierToDelete}) was deleted successfully.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete tier.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveProfile() {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await executeSaveProfile();
      setStatus(`Configuration saved for ${tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected}. Applied globally.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save tier configuration.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyReadiness() {
    if (busy || dirty || selectedRow?.profileRevision == null) return;
    setBusy(true);
    setError("");
    setVerification(null);
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/verify`, {
        method: "POST", body: JSON.stringify({ expectedRevision: selectedRow.profileRevision }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      setVerification(result.checks);
      const verified = result.profile as TierProfileRow;
      if (verified.composedProfile) {
        draftsByTierRef.current[selected] = verified.composedProfile;
        setDraft(verified.composedProfile);
      }
      await loadProfiles(false);
      setStatus(verified.readiness.ready ? "Saved setup verified. Enabled tiers are available to tenants." : "Checks completed. Review the remaining requirements below.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Verification could not finish. Try again.");
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
          ? `${tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected} is now ENABLED for all tenants.`
          : `${tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected} is now DISABLED and hidden from tenants.`
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update tier activation.");
      void loadProfiles(false);
    } finally {
      setBusy(false);
    }
  }

  const currentVoices = useMemo(() => {
    const languages = draft.supportedLanguages;
    return getVoicesForTtsProvider(providers, currentTtsProvider, currentTtsModel, languages, currentTtsModelObj?.voices);
  }, [providers, currentTtsProvider, currentTtsModel, currentTtsModelObj?.voices, draft.supportedLanguages]);

  const currentModelInventory = useMemo(() => {
    const rows = providers.find((entry) => entry.id === currentTtsProvider)?.models?.tts?.find((entry) => entry.id === currentTtsModel)?.voices || [];
    return rows.map((voice) => ({ ...voice,
      id: currentTtsModelObj?.voices.find((item) => item.providerVoiceId === voice.providerVoiceId)?.id || voice.id,
    }));
  }, [providers, currentTtsProvider, currentTtsModel, currentTtsModelObj?.voices]);

  useEffect(() => { setVoiceCategory(""); }, [currentTtsProvider, currentTtsModel]);

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
      const voice = currentVoices.find((item) => item.id === voiceId);
      if (!voice) throw new Error("Choose a current model voice.");
      const response = await portalFetch("dev", "/api/dev/stack/voice-preview", {
        method: "POST",
        body: JSON.stringify({
          provider: currentTtsProvider,
          model: currentTtsModel,
          voiceId: voice.providerVoiceId,
          language: voice.languages[0],
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
  }, [currentTtsProvider, currentTtsModel, currentVoices, playingVoiceId]);

  function handleOpenDuplicateModal() {
    const basePrefix = selected.slice(0, 10).replace(/[^a-z0-9_]/g, "_");
    const existingTiers = new Set(rows.map((r) => r.tier));
    let idx = 1;
    while (existingTiers.has(`${basePrefix}_copy_${idx}`)) {
      idx++;
    }
    const defaultSlug = `${basePrefix}_copy_${idx}`.slice(0, 20);
    const sourceName = tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected;
    setDuplicateNewSlug(defaultSlug);
    setDuplicateLabel(`${sourceName} (Copy ${idx})`);
    setShowDuplicateModal(true);
  }

  async function handleConfirmDuplicate() {
    if (busy) return;
    const slug = duplicateNewSlug.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 20);
    if (!slug) {
      setError("Please enter a valid identifier for the duplicated stack (lowercase letters, numbers, and underscores).");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles/duplicate", {
        method: "POST",
        body: JSON.stringify({
          sourceTier: selected,
          targetTier: slug,
          targetLabel: duplicateLabel.trim() || undefined,
        }),
      });

      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const createdTier = data.tier || slug;
      await loadProfiles(false);
      switchSelectedTier(createdTier);
      setShowDuplicateModal(false);
      setStatus(`Successfully created new duplicated stack "${duplicateLabel || createdTier}" (${createdTier})! Selected and ready for configuration.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not duplicate tier stack.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePrices() {
    if (pricesSaving) return;
    setPricesSaving(true);
    setPricesError("");
    setPricesStatus("");
    try {
      const payload = {
        rateCurrency: "INR",
        webInrPerMin: Number(webInr) || 0,
        didMonthlyInr: Number(numberInr) || 0,
        fxRateInr: Number(fxRate) || 95.64,
        reason: "Updated Platform & Channel Prices (INR) from Stacks & Tiers workbench",
      };
      const res = await portalFetch("dev", "/api/dev/admin/billing-rates", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await responseError(res));
      setPricesStatus("Platform & Channel Prices (INR) saved successfully. Applied globally across all tenants and billing calculations.");
      await loadProfiles(false);
    } catch (err) {
      setPricesError(err instanceof Error ? err.message : "Failed to save prices.");
    } finally {
      setPricesSaving(false);
    }
  }

  const switchTelephony = async (providerId: string) => {
    if (telephonyBusy || telephony?.active_provider === providerId) return;
    setTelephonyBusy(true);
    setTelephonyMsg("");
    setTelephonyError("");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/provider", {
        method: "PATCH",
        body: JSON.stringify({ provider: providerId }),
      });
      if (!r.ok) {
        setTelephonyError(`Failed to switch provider (${r.status})`);
        return;
      }
      await loadTelephony();
      setTelephonyMsg(`Active telephony trunk switched to ${providerId.toUpperCase()}. Direct routing updated.`);
    } catch (e) {
      setTelephonyError(e instanceof Error ? e.message : "Failed to switch provider");
    } finally {
      setTelephonyBusy(false);
    }
  };

  const testHandshake = async () => {
    setTelephonyBusy(true);
    setTelephonyMsg("Testing carrier handshake…");
    setTelephonyError("");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/handshake", { method: "POST" });
      const j = await r.json();
      if (j.ok) {
        setTelephonyMsg(`✓ Handshake OK (${telephony?.active_provider?.toUpperCase()}): Connected to carrier trunk`);
      } else {
        setTelephonyError(`⚠ Handshake warning: ${j.error || JSON.stringify(j)}`);
      }
    } catch (e) {
      setTelephonyError(e instanceof Error ? e.message : "Handshake failed");
    } finally {
      setTelephonyBusy(false);
    }
  };

  async function handleSaveTranscription() {
    if (transcriptionSaving) return;
    setTranscriptionSaving(true);
    setTranscriptionStatus("");
    setTranscriptionError("");
    try {
      const currentOverride: Record<string, unknown> = saasPhoneRaw ? { ...saasPhoneRaw } : { pipeline: "realtime_voice", language: "te-IN" };
      currentOverride.transcription_mode = transcriptionMode;
      currentOverride.transcription_live_model = transcriptionLiveModel;

      const res = await portalFetch("dev", "/api/dev/stack/saas-phone", {
        method: "PUT",
        body: JSON.stringify({
          language: String(currentOverride.language || "te-IN"),
          stack_override: currentOverride,
        }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      setTranscriptionStatus("Transcription configuration saved and applied globally.");
      await loadTranscription();
    } catch (err) {
      setTranscriptionError(err instanceof Error ? err.message : "Failed to save transcription.");
    } finally {
      setTranscriptionSaving(false);
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
            Manage platform prices in INR, configure telephony trunks, and caller transcription settings in one unified workbench.
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
        {allDisplayTiers.map((tier) => {
          const row = rows.find((r) => r.tier === tier);
          const active = selected === tier;
          const tierEnabled = row?.readiness?.enabled === true;
          const label = row?.label || DEFAULT_TIER_LABELS[tier] || tier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

          return (
            <button
              key={tier}
              type="button"
              disabled={busy}
              onClick={() => switchSelectedTier(tier)}
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
                  {tierEnabled ? (row?.readiness.ready ? "Active / Ready" : "Enabled · verification needed") : "Disabled"}
                </span>
                {row?.composedProfile?.retailRateInr ? (
                  <span className="font-mono text-[11px] text-text-subtle">
                    · ₹{Number(row.composedProfile.retailRateInr).toFixed(2)}/min
                  </span>
                ) : row?.retailRate?.inrPaisePerMin ? (
                  <span className="font-mono text-[11px] text-text-subtle">
                    · ₹{(row.retailRate.inrPaisePerMin / 100).toFixed(2)}/min
                  </span>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      <div
        role="tablist"
        aria-label="Voice stack configuration sections"
        className="flex flex-wrap gap-1.5 rounded-2xl border border-surface-border bg-surface-card p-1.5"
      >
        {PROFILE_SECTIONS.map((tab) => {
          const active = activeSection === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`pstn-section-tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`pstn-section-panel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setActiveSection(tab.id)}
              onKeyDown={(event) => {
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                event.preventDefault();
                const current = PROFILE_SECTIONS.findIndex((section) => section.id === activeSection);
                const step = event.key === "ArrowRight" ? 1 : -1;
                const next = PROFILE_SECTIONS[(current + step + PROFILE_SECTIONS.length) % PROFILE_SECTIONS.length];
                setActiveSection(next.id);
                document.getElementById(`pstn-section-tab-${next.id}`)?.focus();
              }}
              className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 ${
                active
                  ? "bg-accent-dim text-text shadow-sm ring-1 ring-accent-primary/40"
                  : "text-text-muted hover:bg-surface-raised/60 hover:text-text"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Selected Tier Management Panel */}
      <div
        role="tabpanel"
        id="pstn-section-panel-stack"
        aria-labelledby="pstn-section-tab-stack"
        hidden={activeSection !== "stack"}
      >
      <DevCard
        title={`${tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected} Configuration`}
        description="Select the provider and model for STT, LLM, and TTS. Changes apply to all new tenant calls in this tier."
      >
        {/* Tier Controls Bar (Name + Enable/Disable Toggle + Duplicate Stack) */}
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
                placeholder={DEFAULT_TIER_LABELS[selected] || selected}
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

            {/* Tier Actions (Duplicate + Delete) */}
            <div className="flex flex-col gap-1.5 md:items-end">
              <span className="text-xs font-medium text-text-muted">Tier Actions</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleOpenDuplicateModal}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text hover:border-surface-border-subtle hover:bg-surface-raised transition-colors shadow-sm"
                  title="Replicate this stack configuration as a new tier"
                >
                  <span>📋 Duplicate</span>
                </button>
                {!["low", "medium", "premium"].includes(selected) && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDeleteTier(selected)}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 transition-colors shadow-sm"
                    title="Permanently delete this custom tier"
                  >
                    <span>🗑️ Delete Tier</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Tier Pricing & Provider Cost Configuration */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 mb-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3 mb-4">
            <div className="flex items-center gap-2">
              <span className="text-base">💰</span>
              <h3 className="text-sm font-semibold text-text">Tier Pricing & Provider Cost</h3>
            </div>
            <span className="text-[11px] font-mono text-text-subtle">Direct Platform Economics · Applied Universally</span>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="block text-xs font-semibold text-text mb-1">
                Platform Calling Price (₹/min)
                <span className="text-text-muted font-normal ml-1">· Billed to Tenants</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-sm font-semibold text-text-muted">₹</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  value={retailRateInput}
                  onChange={(e) => handleRetailRateChange(e.target.value)}
                  placeholder="e.g. 5.00"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel pl-7 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>
              <p className="mt-1 text-[11px] text-text-subtle">
                Retail price per minute deducted from tenant wallets when placing phone calls on this tier.
              </p>
            </div>

            <div>
              <label htmlFor="tier-web-rate" className="block text-xs font-semibold text-text mb-1">Web agent price (₹/min)</label>
              <input id="tier-web-rate" type="number" min="0.01" step="0.01" value={draft.webRetailRateInr ?? ""}
                onChange={(event) => handleWebRateChange(event.target.value)}
                placeholder={selectedRow?.webRetailRate?.inrPaisePerMin ? `${selectedRow.webRetailRate.inrPaisePerMin / 100}` : "Use saved web default"}
                className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text font-mono" />
              <p className="mt-1 text-[11px] text-text-subtle">Browser and embedded web calls on this stack. Blank uses the saved global web default. Each call locks its price at start.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text mb-1">
                Estimated Provider / Supplier Cost (₹/min)
                <span className="text-text-muted font-normal ml-1">· Admin Wholesale Cost</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-sm font-semibold text-text-muted">₹</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  value={supplierCostInput}
                  onChange={(e) => handleSupplierCostChange(e.target.value)}
                  placeholder="e.g. 1.80"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel pl-7 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>
              <p className="mt-1 text-[11px] text-text-subtle">
                Estimated cost to platform for telephony trunk + STT + LLM + TTS for accurate profit margin tracking.
              </p>
            </div>
          </div>
        </div>

        {/* Gemini 3.8 Live (Flagship) Native Architecture Callout */}
        {selected === "premium" && (
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 mb-6 text-sm text-indigo-100">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">⚡</span>
              <h4 className="font-semibold text-indigo-200">Gemini 3.8 Live (Flagship) Native Realtime Architecture</h4>
            </div>
            <p className="text-xs text-indigo-200/90 leading-relaxed mb-3">
              Gemini 3.8 Live is our flagship unified bidirectional multimodal speech agent. Unlike modular composed tiers, Speech-to-Text (STT), reasoning intelligence (LLM), and speech generation (TTS) operate end-to-end within a single ultra-low-latency WebSocket connection (<code className="font-mono bg-indigo-950/60 px-1 py-0.5 rounded text-indigo-300">server/realtime/</code>).
            </p>
            <div className="grid gap-3 sm:grid-cols-2 text-xs">
              <div className="rounded-lg bg-indigo-950/50 border border-indigo-500/20 p-3">
                <span className="font-semibold text-indigo-300 block mb-1">🧠 Direct In-Session Context (No Dynamic Caching)</span>
                <p className="text-indigo-200/80 text-[11px] leading-relaxed">
                  The 3.8 Live session retains dialogue memory organically inside the open carrier stream. Server-side dynamic memory caching—which is utilized to bridge intermediate STT and LLM turns in the Economical and Standard composed tiers—is completely bypassed, minimizing turn latency and eliminating token re-injection overhead.
                </p>
              </div>
              <div className="rounded-lg bg-indigo-950/50 border border-indigo-500/20 p-3">
                <span className="font-semibold text-indigo-300 block mb-1">📞 Zero-Hangup PSTN Trunk Alignment</span>
                <p className="text-indigo-200/80 text-[11px] leading-relaxed">
                  Pre-buffers audio greetings upon carrier media readiness before database call record finalization to eliminate answer-race hangups. Bidirectional turn-taking is guarded with acoustic echo suppression and a 350ms speech onset threshold.
                </p>
              </div>
            </div>
          </div>
        )}

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
                  aria-label="STT provider"
                  value={draft.stt.provider}
                  onChange={(e) => handleSttProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
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
                  aria-label="STT model"
                  value={draft.stt.model}
                  onChange={(e) => handleSttModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
                  {currentSttModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              Streaming audio chunk recognition over low-latency WebSockets. The selected recognition model stays bound to this stack.
            </p>
          </div>

          {/* 2. Intelligence / LLM */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-purple-500/20 text-xs font-bold text-purple-400">
                  2
                </span>
                <h3 className="text-sm font-semibold text-text">Intelligence (LLM)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Reasoning</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  LLM Provider
                </label>
                <select
                  aria-label="LLM provider"
                  value={draft.llm.provider}
                  onChange={(e) => handleLlmProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
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
                  aria-label="LLM model"
                  value={draft.llm.modelId}
                  onChange={(e) => handleLlmModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
                  {currentLlmModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              System instructions, dynamic persona rules, and dialogue turns are executed on this model.
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
                  aria-label="TTS provider"
                  value={currentTtsProvider}
                  onChange={(e) => handleTtsProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
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
                  aria-label="TTS model"
                  value={currentTtsModel}
                  onChange={(e) => handleTtsModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
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
              Curated voice personas are automatically bound to this speech engine. All speech options stream over low-latency WebSockets.
            </p>
          </div>
        </div>

        {/* Acoustic Calibration & Speech Dynamics (Universal Platform Controls) */}
        <div className="mt-6 rounded-2xl border border-surface-border bg-gradient-to-b from-surface-card to-surface-raised/40 p-5 shadow-sm space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border-subtle pb-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-xl bg-accent-primary/20 text-accent-primary font-bold text-sm">
                  🎛️
                </span>
                <h3 className="text-base font-semibold text-text">
                  Acoustic Calibration &amp; Speech Dynamics
                </h3>
                <span className="rounded-full border border-purple-500/30 bg-purple-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-purple-300">
                  Universal Defaults
                </span>
              </div>
              <p className="text-xs text-text-muted">
                {isNativeRealtimeLlm
                  ? <>Fine-tune the native live voice pace. This tier speaks through the realtime voice, so no separate TTS engine is active.</>
                  : <>Only the knobs supported by <strong>{currentTtsProvider ? currentTtsProvider.toUpperCase() : "the selected engine"}</strong> are shown. Every saved value is applied to all platform calls.</>}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg">
                ⚡ Universal Platform Default: Applied to all calls
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {currentTtsKnobs.map((spec) => (
              <span
                key={spec.key}
                className="inline-flex items-center gap-1.5 rounded-full border border-surface-border bg-surface-raised px-2.5 py-1 text-[10px] font-medium text-text-muted"
              >
                <span className="size-1.5 rounded-full bg-emerald-400" />
                {spec.label}
                {spec.native ? <code className="text-[9px] text-text-subtle">{spec.native}</code> : null}
              </span>
            ))}
          </div>

          {/* Dynamic Knobs — driven by the selected model's catalog capability list */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-3 rounded-xl border border-surface-border/60 bg-surface-panel/70 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-text block">{speedKnob.label}</span>
                  <span className="text-[10px] text-text-subtle">{speedKnob.description}</span>
                </div>
                <span className="font-mono text-xs font-bold text-accent-primary px-2 py-0.5 rounded bg-accent-primary/10 border border-accent-primary/20">
                  {Number(draft.voiceDynamics?.speed ?? speedKnob.default ?? 1.0).toFixed(2)}{speedKnob.unit || "x"}
                </span>
              </div>

              <input
                type="range"
                min={speedKnob.min}
                max={speedKnob.max}
                step={speedKnob.step || 0.05}
                value={Number(draft.voiceDynamics?.speed ?? speedKnob.default ?? 1.0)}
                onChange={(e) => handleDynamicsChange({ speed: parseFloat(e.target.value) })}
                className="w-full h-2 bg-surface-raised rounded-lg appearance-none cursor-pointer accent-accent-primary"
              />

              <div className="flex justify-between text-[10px] text-text-subtle font-mono">
                <span>{Number(speedKnob.min).toFixed(2)}{speedKnob.unit || "x"} (Slow)</span>
                <span className="text-accent-primary font-semibold">1.00{speedKnob.unit || "x"} (Standard)</span>
                <span>{Number(speedKnob.max).toFixed(2)}{speedKnob.unit || "x"} (Fast)</span>
              </div>

              <div className="pt-2 border-t border-surface-border-subtle">
                <span className="text-[10px] font-semibold text-text-muted uppercase block mb-1.5">
                  Pacing Presets ({isNativeRealtimeLlm ? "LIVE VOICE" : currentTtsProvider.toUpperCase()})
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {speedPresetsFor(speedKnob).map((preset) => {
                    const active = Math.abs(Number(draft.voiceDynamics?.speed ?? 1.0) - preset.value) < 0.01;
                    return (
                      <button
                        key={`${preset.label}-${preset.value}`}
                        type="button"
                        onClick={() => handleDynamicsChange({ speed: preset.value })}
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                          active
                            ? "bg-accent-primary text-white shadow-xs"
                            : "border border-surface-border bg-surface-raised text-text hover:bg-surface-raised/80"
                        }`}
                      >
                        {preset.label} ({preset.value.toFixed(2)}x)
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="space-y-4 rounded-xl border border-surface-border/60 bg-surface-panel/70 p-4">
              {secondaryKnobs.length === 0 ? (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-text block">No additional delivery knobs</span>
                  <p className="text-[11px] text-text-subtle">
                    {isNativeRealtimeLlm
                      ? "The native live voice exposes pace only; tone and expression come from the voice model itself. Unsupported settings are never sent."
                      : "This engine exposes speaking pace only. Other controls are hidden because the provider would ignore them."}
                  </p>
                </div>
              ) : (
                secondaryKnobs.map((spec, index) => {
                  const raw = dynamicsValue(draft.voiceDynamics, spec.key);
                  if (spec.kind === "select") {
                    const current = String(raw ?? spec.default ?? "");
                    return (
                      <div key={spec.key} className={index > 0 ? "pt-3 border-t border-surface-border-subtle" : ""}>
                        <label className="block text-xs font-medium text-text-muted mb-1">{spec.label}</label>
                        <select
                          value={current}
                          onChange={(e) => handleDynamicsChange(knobPatch(spec.key, e.target.value))}
                          className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                        >
                          {(spec.options || []).map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                        {spec.description ? <p className="mt-1 text-[10px] text-text-subtle">{spec.description}</p> : null}
                      </div>
                    );
                  }
                  const current = Number(raw ?? spec.default ?? 1);
                  return (
                    <div key={spec.key} className={index > 0 ? "space-y-2 pt-3 border-t border-surface-border-subtle" : "space-y-2"}>
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-xs font-semibold text-text block">{spec.label}</span>
                          <span className="text-[10px] text-text-subtle">{spec.description}</span>
                        </div>
                        <span className="font-mono text-xs font-bold text-accent-primary px-2 py-0.5 rounded bg-accent-primary/10 border border-accent-primary/20">
                          {current.toFixed(2)}{spec.unit || ""}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={spec.min}
                        max={spec.max}
                        step={spec.step || 0.01}
                        value={current}
                        onChange={(e) => handleDynamicsChange(knobPatch(spec.key, parseFloat(e.target.value)))}
                        className="w-full h-2 bg-surface-raised rounded-lg appearance-none cursor-pointer accent-accent-primary"
                      />
                      <div className="flex justify-between text-[10px] text-text-subtle font-mono">
                        <span>{Number(spec.min).toFixed(2)}{spec.unit || ""} (Low)</span>
                        <span className="text-accent-primary font-semibold">{Number(spec.default ?? 1).toFixed(2)}{spec.unit || ""} (Default)</span>
                        <span>{Number(spec.max).toFixed(2)}{spec.unit || ""} (High)</span>
                      </div>
                    </div>
                  );
                })
              )}

              {currentTtsProvider === "gnani" && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Expressive Audio Tags</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      {currentTtsModel === "timbre-v3.0" ? "Timbre v3.0" : "Timbre v2.5"}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    {currentTtsModel === "timbre-v3.0"
                      ? "Timbre v3.0 accepts inline expressive audio tags. Speaking speed is the documented numeric delivery control; numeric pitch, volume and temperature are not documented by the provider."
                      : "Timbre v2.5 supports speaking speed. Expressive audio tags are available on Timbre v3.0 only; numeric pitch, volume and temperature are not documented by the provider."}
                  </p>
                </div>
              )}

              {currentTtsProvider === "cartesia" && (
                <p className="pt-2 border-t border-surface-border-subtle text-[11px] text-text-subtle" data-testid="cartesia-delivery-guidance">
                  Sonic offers all 58 documented emotion choices for English. Emotion, speed and volume are generation guidance;
                  results depend on the voice and transcript. Saved choices are included in every synthesis request.
                </p>
              )}

              {currentTtsProvider === "gemini" && !isNativeRealtimeLlm && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Delivery Persona Modulation</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      Speech Metadata
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    Pace and pitch character are sent as speech metadata directions on every turn; Gemini has no numeric pitch, temperature, or volume parameters.
                  </p>
                </div>
              )}

              {currentTtsProvider === "sarvam" && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Model Knob Matrix</span>
                    <span className="text-[10px] font-mono text-sky-300 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
                      Per-model
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    v3 and v4-flash expose pace + temperature. v2 exposes pace + pitch + loudness. Only parameters accepted by the selected model are sent.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Test Speed Dynamics & Live Audition Box */}
          <div className="rounded-xl border border-surface-border bg-surface-panel p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text">
                  🎧 Test Speed &amp; Dynamics Audio Generator
                </span>
                <span className="text-[10px] text-text-subtle font-mono">
                  (Audition live with configured pace)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={testVoiceId || currentVoices[0]?.id || ""}
                  onChange={(e) => setTestVoiceId(e.target.value)}
                  className="rounded-lg border border-surface-border bg-surface-raised px-2.5 py-1 text-xs text-text focus:outline-none"
                >
                  {currentVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      Voice: {v.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Test Sample Text Input */}
            <div className="space-y-2">
              <label className="block text-xs font-medium text-text-muted">
                Audition Sample Text (Telugu / English / Hindi)
              </label>
              <textarea
                rows={2}
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                placeholder="Enter test script to synthesize with configured dynamics..."
                className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-sans resize-none"
              />

              {/* Preset Sample Text Chips */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[10px] text-text-subtle mr-1">Quick Scripts:</span>
                {[
                  {
                    label: "Real Estate Mohan (Telugu)",
                    text: "నమస్కారం! నేను మీ రియల్ ఎస్టేట్ సేల్స్ అసిస్టెంట్ మోహన్‌ని. మీకు ఎలా సహాయపడగలను?",
                  },
                  {
                    label: "Real Estate Mohan (English)",
                    text: "Hello! This is Mohan from real estate sales. How can I help you explore prime properties today?",
                  },
                  {
                    label: "Customer Support (Hindi)",
                    text: "नमस्ते! मैं आपका रियल एस्टेट सेल्स कंसल्टेंट मोहन हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
                  },
                ].map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    onClick={() => setTestText(s.text)}
                    className="rounded-md border border-surface-border bg-surface-raised/70 px-2 py-0.5 text-[10px] text-text-muted hover:text-text hover:bg-surface-raised transition-all"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Audition Trigger & Status */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  disabled={isTestingDynamics}
                  onClick={() => void handleTestSpeedDynamics()}
                  className={`flex items-center gap-2 px-4 py-2 text-xs font-medium transition-all ${
                    isPlayingDynamics
                      ? "bg-amber-600 hover:bg-amber-700 text-white"
                      : "bg-accent-primary hover:bg-accent-primary/90 text-white shadow-sm"
                  }`}
                >
                  {isTestingDynamics ? (
                    <>
                      <span className="size-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      <span>Synthesizing Audio…</span>
                    </>
                  ) : isPlayingDynamics ? (
                    <>
                      <span>⏹ Stop Audition</span>
                    </>
                  ) : (
                    <>
                      <span>▶ Generate &amp; Audition Dynamics</span>
                    </>
                  )}
                </Button>

                {isPlayingDynamics && (
                  <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg animate-pulse">
                    <span className="size-2 rounded-full bg-emerald-400" />
                    <span>Playing at {Number(draft.voiceDynamics?.speed || 1.0).toFixed(2)}x Speed ({currentTtsProvider.toUpperCase()})</span>
                  </div>
                )}
              </div>

              <span className="text-[11px] text-text-subtle font-mono">
                API: POST /api/dev/stack/voice-preview
              </span>
            </div>
          </div>
        </div>

        {/* Global Prewarm Greeting Synthesis Configuration Card */}
        <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2.5">
                <div className={`p-1.5 rounded-lg ${prewarmGreetingEnabled ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-surface-border/20 text-text-muted"}`}>
                  <span className="text-sm">⚡</span>
                </div>
                <h4 className="text-sm font-semibold text-text">
                  Global Prewarm Greeting (Instant First Audio)
                </h4>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
                    prewarmGreetingEnabled
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : "bg-surface-border/20 text-text-subtle border-surface-border/40"
                  }`}
                >
                  {prewarmGreetingEnabled ? "Active (Global)" : "Disabled (Standard Playout)"}
                </span>
              </div>
              <p className="mt-2 text-xs text-text-muted leading-relaxed">
                Pre-synthesizes the outbound agent greeting during carrier ring and connection time so caller hears the opening instantly (&lt;200ms) upon answering. Applies to all PSTN calls globally. When disabled, the agent synthesizes greeting on live stream pickup.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[10px] font-mono text-text-subtle">
                  API: PATCH /api/dev/stack/prewarm-greeting
                </span>
                <span className="text-[10px] text-text-subtle">·</span>
                <span className="text-[10px] text-text-subtle">
                  Scope: Universal Platform
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={prewarmLoading}
                onClick={() => void togglePrewarmGreeting(!prewarmGreetingEnabled)}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2 ${
                  prewarmGreetingEnabled ? "bg-emerald-500" : "bg-surface-border"
                } ${prewarmLoading ? "opacity-50 cursor-not-allowed" : ""}`}
                role="switch"
                aria-checked={prewarmGreetingEnabled}
                aria-label="Toggle Prewarm Greeting"
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block size-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    prewarmGreetingEnabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
              <span className="text-xs font-medium text-text select-none min-w-[58px]">
                {prewarmGreetingEnabled ? "Enabled" : "Disabled"}
              </span>
            </div>
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
                {currentModelInventory.length} provider voices in the complete model catalogue · {currentVoices.length} available for the configured languages.
              </p>
            </div>
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
              Provider voice catalog
            </span>
          </div>

          {/* Voice Preview Playback Grid */}
          <div className="mb-3 flex items-center gap-3">
            <label className="text-xs text-text-muted">Voice style
              <select aria-label="Voice style" value={voiceCategory} onChange={(event) => setVoiceCategory(event.target.value)} className="ml-2 rounded-lg border border-surface-border bg-surface-panel p-2">
                <option value="">All styles</option>
                {[...new Set(currentModelInventory.map((voice) => voice.category).filter(Boolean))].sort().map((category) => <option key={category} value={category}>{category}</option>)}
              </select>
            </label>
            <Button variant="secondary" disabled={catalogRefreshing} onClick={() => void loadCatalog(true)}>{catalogRefreshing ? "Refreshing voices…" : "Refresh provider voices"}</Button>
            {catalogError && <p role="alert" className="text-xs text-red-400">{catalogError}</p>}
          </div>
          <div role="region" aria-label="Available model voices" tabIndex={0} className="grid max-h-96 overflow-y-auto gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {currentModelInventory.map((v, index) => ({ ...v, number: index + 1 })).filter((voice) => !voiceCategory || voice.category === voiceCategory).map((v) => {
              const isPlaying = playingVoiceId === v.id;
              const isLoading = previewLoadingId === v.id;
              const available = currentVoices.some((voice) => voice.id === v.id);
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
                    <p className="text-xs font-medium text-text truncate">{v.label || `Voice ${v.number}`}</p>
                    <p className="text-[10px] text-text-muted break-all">{v.providerVoiceId}</p>
                    <p className="text-[10px] text-text-muted">{v.category || ""} · {(v.languages.length ? v.languages : v.preferredLanguages || []).join(", ")}</p>
                    {!available && <p className="text-[10px] text-amber-300">
                      {v.unavailableReason || "Enable one of this voice's supported languages to audition it."}
                    </p>}
                    {(v.gender || v.tone) && (
                      <p className="text-[10px] text-text-subtle truncate">
                        {v.gender ? `${v.gender} · ` : ""}{v.tone || ""}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    disabled={isLoading || !available}
                    aria-label={`Preview ${v.label || v.providerVoiceId}`}
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

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border p-4">
          <p className="max-w-xl text-xs text-text-muted">Verify the saved model, speech, tools, credentials and media path with synthetic provider requests. No phone call is placed. Capacity is a concurrency smoke check, not a peak-load certification.</p>
          <Button type="button" variant="secondary" disabled={busy || dirty || !selectedRow?.composedProfile || draft.llm.apiMode === "websocket"}
            onClick={() => void handleVerifyReadiness()} data-testid="verify-profile-readiness">
            {busy ? "Working…" : "Verify saved setup"}
          </Button>
        </div>
        {verification && <ul className="mt-3 space-y-2 text-xs" aria-label="Verification results">
          {Object.entries(verification).map(([key, check]) => <li key={key} className={check.passed ? "text-emerald-300" : "text-amber-300"}>
            {check.passed ? "Passed" : "Needs attention"}: {check.detail}
          </li>)}
        </ul>}

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
            {autoSaveStatus && (
              <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 rounded-full animate-pulse">
                {autoSaveStatus}
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
                setTierLabelInput(DEFAULT_TIER_LABELS[selected] || selected);
                setDirty(true);
              }}
            >
              Load Recommended Default
            </Button>
          </div>
        </div>
      </DevCard>
      </div>

      {/* Platform & Channel Prices (INR) Card */}
      <div
        role="tabpanel"
        id="pstn-section-panel-pricing"
        aria-labelledby="pstn-section-tab-pricing"
        hidden={activeSection !== "pricing"}
      >
      <DevCard
        title="Platform & Channel Prices (INR)"
        description="Web calling, number rental and exchange-rate settings. Phone-call prices are managed once, inside each voice stack."
      >
        {pricesError && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
            {pricesError}
          </div>
        )}
        {pricesStatus && (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            {pricesStatus}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Web Calling Rate */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
            <label className="block text-xs font-semibold text-text">
              Default Web Calling Rate
            </label>
            <p className="text-[11px] text-text-muted">Used only when the selected stack has no separate web price. Configure overrides in each stack’s pricing section.</p>
            <div className="relative mt-1">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={webInr}
                onChange={(e) => setWebInr(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              />
            </div>
          </div>

          {/* Phone DID Rental Rate */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
            <label className="block text-xs font-semibold text-text">
              DID Phone Number Rental
            </label>
            <p className="text-[11px] text-text-muted">Monthly leased virtual carrier phone number in ₹</p>
            <div className="relative mt-1">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
              <input
                type="number"
                step="1"
                min="0"
                value={numberInr}
                onChange={(e) => setNumberInr(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              />
            </div>
          </div>

          {/* FX Exchange Rate */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold text-text">USD → INR FX Rate</label>
              {liveFx ? (
                <span className="text-[10px] font-mono text-emerald-400">
                  Live: ₹{liveFx.toFixed(2)}
                </span>
              ) : null}
            </div>
            <p className="text-[11px] text-text-muted">Platform charge FX rate (rupees per USD)</p>
            <div className="relative mt-1">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-xs text-text-muted">₹</span>
              <input
                type="number"
                step="0.01"
                min="50"
                value={fxRate}
                onChange={(e) => setFxRate(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-raised pl-8 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              />
            </div>
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
          <p className="text-xs text-text-subtle">
            All entered rates apply immediately to platform calls and wallet balance calculations.
          </p>
          <Button
            type="button"
            disabled={pricesSaving}
            onClick={() => void handleSavePrices()}
            className="px-5 py-2.5"
          >
            {pricesSaving ? "Saving Prices…" : "Save Platform Prices"}
          </Button>
        </div>
      </DevCard>
      </div>

      {/* Telephony Infrastructure & PSTN Calling Trunk Card */}
      <div
        role="tabpanel"
        id="pstn-section-panel-telephony"
        aria-labelledby="pstn-section-tab-telephony"
        hidden={activeSection !== "telephony"}
      >
      <DevCard
        title="Telephony Infrastructure & PSTN Calling Trunk"
        description="Select and manage wholesale carrier trunks for inbound and outbound calls, DID provisioning, and bidirectional audio streaming."
      >
        {telephonyError && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
            {telephonyError}
          </div>
        )}
        {telephonyMsg && (
          <div className="mb-4 rounded-xl border border-accent/30 bg-accent/10 p-3 text-xs font-mono text-accent">
            {telephonyMsg}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {/* Telnyx Trunk Card */}
          {(() => {
            const telnyxSt = telephony?.providers?.find((p) => p.id === "telnyx");
            const isTelnyxActive = (telephony?.active_provider || "vobiz") === "telnyx";
            const isReady = Boolean(telnyxSt?.ready);
            return (
              <div
                className={`rounded-xl border p-4 text-left transition-all ${
                  isTelnyxActive
                    ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                    : "border-border bg-surface-card hover:border-accent/40"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-text">Telnyx PSTN Trunk</p>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                      isReady ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {isReady ? "✓ Ready" : "⚠ Incomplete"}
                  </span>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  Call Control v2 · 8 kHz µ-law · WebSocket media streaming
                </p>
                <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                  <div>Caller ID: {telnyxSt?.phone_number || "Auto"}</div>
                  <div>Connection ID: {telnyxSt?.connection_id || "Configured"}</div>
                  <div>Webhook: /api/telnyx/webhook</div>
                  <div>Stream: /ws/telnyx-stream</div>
                </div>
                <div className="mt-4">
                  <Button
                    type="button"
                    variant={isTelnyxActive ? "primary" : "secondary"}
                    disabled={isTelnyxActive || telephonyBusy}
                    onClick={() => void switchTelephony("telnyx")}
                    className="w-full text-xs"
                  >
                    {isTelnyxActive ? "Active Trunk" : "Switch to Telnyx"}
                  </Button>
                </div>
              </div>
            );
          })()}

          {/* Vobiz Trunk Card */}
          {(() => {
            const vobizSt = telephony?.providers?.find((p) => p.id === "vobiz");
            const isVobizActive = (telephony?.active_provider || "vobiz") === "vobiz";
            const isReady = Boolean(vobizSt?.ready);
            return (
              <div
                className={`rounded-xl border p-4 text-left transition-all ${
                  isVobizActive
                    ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                    : "border-border bg-surface-card hover:border-accent/40"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-text">Vobiz Telephony (Primary Trunk)</p>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                      isReady ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {isReady ? "✓ Ready" : "⚠ Incomplete"}
                  </span>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  Voice XML + Bidirectional L16/µ-law WebSocket stream
                </p>
                <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                  <div>Auth ID: {vobizSt?.account_info?.auth_id || "MA_LX2CKOU1"}</div>
                  <div>App ID: {vobizSt?.account_info?.app_id || "551682"}</div>
                  <div>Answer URL: /api/vobiz/answer</div>
                  <div>Stream: /ws/vobiz-stream</div>
                </div>
                <div className="mt-4">
                  <Button
                    type="button"
                    variant={isVobizActive ? "primary" : "secondary"}
                    disabled={isVobizActive || telephonyBusy}
                    onClick={() => void switchTelephony("vobiz")}
                    className="w-full text-xs"
                  >
                    {isVobizActive ? "Active Trunk" : "Switch to Vobiz"}
                  </Button>
                </div>
              </div>
            );
          })()}
        </div>

        <div className="mt-6 pt-4 border-t border-border flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={telephonyBusy}
              onClick={() => void testHandshake()}
              className="text-xs"
            >
              Test Live Handshake
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={telephonyBusy}
              onClick={() => void loadTelephony()}
              className="text-xs"
            >
              Refresh Trunk Status
            </Button>
          </div>
          <span className="font-mono text-xs text-text-subtle">
            Trunk controls are isolated to platform infrastructure.
          </span>
        </div>
      </DevCard>
      </div>

      {/* Transcription Mode & Caller Transcripts Card */}
      <div
        role="tabpanel"
        id="pstn-section-panel-transcription"
        aria-labelledby="pstn-section-tab-transcription"
        hidden={activeSection !== "transcription"}
      >
      <DevCard
        title="Transcription Mode & Caller Transcripts"
        description="Choose when and how caller speech is transcribed into text records during PSTN telephone conversations."
      >
        {transcriptionError && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
            {transcriptionError}
          </div>
        )}
        {transcriptionStatus && (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            {transcriptionStatus}
          </div>
        )}

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              {
                id: "off" as const,
                title: "Off",
                detail: "No caller transcripts recorded. Reduces processing overhead for high-throughput calls.",
              },
              {
                id: "live" as const,
                title: "Live transcription",
                detail: "Caller speech transcribed in real time during the call using the selected recognizer below.",
              },
              {
                id: "post_call" as const,
                title: "Post-call — Gemini 3.5 Transcribe",
                detail: "~$0.005/min batch processed from recording after call hangs up.",
              },
            ].map((opt) => (
              <label
                key={opt.id}
                className={`flex flex-col rounded-xl border p-4 cursor-pointer transition-all ${
                  transcriptionMode === opt.id
                    ? "border-accent-primary bg-accent-dim shadow-sm"
                    : "border-surface-border bg-surface-card hover:bg-surface-raised/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="workbenchTranscriptionMode"
                    checked={transcriptionMode === opt.id}
                    onChange={() => setTranscriptionMode(opt.id)}
                    className="accent-accent-primary"
                  />
                  <span className="font-semibold text-xs text-text">{opt.title}</span>
                </div>
                <p className="mt-2 text-xs text-text-muted leading-relaxed">{opt.detail}</p>
              </label>
            ))}
          </div>

          {transcriptionMode === "live" && (
            <div className="mt-4 rounded-xl border border-surface-border bg-surface-raised/40 p-4 space-y-2">
              <label className="block text-xs font-semibold text-text">
                Live Transcription Recognizer Model
              </label>
              <select
                value={transcriptionLiveModel}
                onChange={(e) => setTranscriptionLiveModel(e.target.value)}
                className="w-full sm:max-w-md rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-xs text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              >
                <option value="gpt-4o-mini-transcribe">GPT-4o Mini Transcribe · ~$0.003/min</option>
                <option value="gpt-transcribe">GPT-Transcribe · ~$0.0045/min</option>
                <option value="saaras:v3-realtime">Sarvam Saaras Realtime · ~₹0.50/min</option>
                <option value="gemini-native">Gemini Native · In-session tokens</option>
              </select>
              <p className="text-[11px] text-text-subtle">
                The recognizer receives the inbound caller audio stream and writes live speech transcripts to the database.
              </p>
            </div>
          )}

          <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
            <span className="text-xs text-text-subtle">
              Applies globally to new inbound and outbound PSTN calls.
            </span>
            <Button
              type="button"
              disabled={transcriptionSaving}
              onClick={() => void handleSaveTranscription()}
              className="px-5 py-2.5"
            >
              {transcriptionSaving ? "Saving…" : "Save Transcription Settings"}
            </Button>
          </div>
        </div>
      </DevCard>
      </div>

      {/* Duplicate Stack Modal */}
      {showDuplicateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-semibold text-text">Duplicate Stack as Brand New Tier</h3>
            <p className="text-xs text-text-muted">
              Creates a <strong>completely new, independent voice stack</strong> cloning all STT, LLM, TTS models,
              WebSocket options, and voice configurations from <strong>{tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected}</strong>.
              The existing stack will NOT be overwritten.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  Source Stack (Selected)
                </label>
                <div className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs font-mono text-text-subtle">
                  {tierLabelInput || DEFAULT_TIER_LABELS[selected] || selected} ({selected})
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  New Stack Name (Display Label)
                </label>
                <input
                  type="text"
                  value={duplicateLabel}
                  onChange={(e) => setDuplicateLabel(e.target.value)}
                  placeholder="e.g. Economical Tier (Copy 1)"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  New Tier Identifier / Slug (Max 20 chars, lowercase alphanumeric &amp; underscore)
                </label>
                <input
                  type="text"
                  maxLength={20}
                  value={duplicateNewSlug}
                  onChange={(e) => setDuplicateNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 20))}
                  placeholder="e.g. low_copy_1"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
                <span className="mt-1 block text-[11px] text-text-subtle">
                  Slug: <code className="font-mono text-text">{duplicateNewSlug || "none"}</code>
                </span>
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
                {busy ? "Duplicating…" : "Create Duplicated Stack"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
