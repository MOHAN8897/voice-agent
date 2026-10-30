import type { ReactNode } from "react";

export type ProfileTier = string;

export type StageProfile = { provider: string; model: string };
export type LlmProfile = { provider: string; modelId: string; apiMode: string };
export type VoiceProfile = {
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
export type ModelProfile = {
  id: string;
  label: string;
  provider: string;
  model: string;
  apiMode: string;
  voices: VoiceProfile[];
};
export type EngineProfile = { id: string; label: string; models: ModelProfile[] };
export type ProfileEvidence = {
  sarvamModelAccess: boolean;
  sttVerified: boolean;
  ttsCatalogVerified: boolean;
  toolsVerified: boolean;
  capacityVerified: boolean;
  mediaFormatsVerified: boolean;
  credentialRefConfigured: boolean;
};
export type VoiceDynamics = {
  speed: number;
  pitch?: number;
  temperature?: number;
  emotion?: string;
  volume?: number;
};
export type TtsKnobOption = { value: string; label: string };
export type TtsKnobKey = "speed" | "pitch" | "temperature" | "emotion" | "volume";
export type TtsKnobSpec = {
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
export type ComposedProfile = {
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
  disabledReason?: DisabledReason;
};
export type DisabledReason = { code: string; message: string; at?: string; actor?: string };
export type ReadinessBlocker = { code: string; message: string };
export type RetailRate = { complete?: boolean; usdMicrosPerMin?: number; inrPaisePerMin?: number; fxRateInr?: number; version?: number; source?: string } | null;
export type EffectiveDynamicsRow = {
  engineId?: string;
  modelId?: string;
  provider: string;
  model: string;
  supportedKnobs: string[];
  applied: Record<string, number | string>;
  ignored: string[];
};
export type VerificationCheck = { passed: boolean | null; detail: string; notApplicable?: boolean };
export type TierProfileRow = {
  tier: ProfileTier;
  label?: string;
  profileRevision: number | null;
  composedProfile: ComposedProfile | null;
  readiness: {
    ready: boolean;
    enabled: boolean;
    blockers: ReadinessBlocker[];
    verificationPath?: "test_studio" | "synthetic_checks";
    disabledReason?: DisabledReason;
  };
  retailRate: RetailRate;
  webRetailRate?: RetailRate;
  readOnly?: boolean;
  priceSource?: "tier_card" | "billing_rate_version" | "missing";
  native?: boolean;
  public?: boolean;
  effectiveVoiceDynamics?: EffectiveDynamicsRow[];
  verification?: { checkedAt?: string; checks?: Record<string, VerificationCheck>; native?: boolean };
};
export type ProfilesResponse = { environment: string; profiles: TierProfileRow[] };
export type CatalogModel = { id: string; label?: string; realtime?: boolean; api_mode?: string; api_modes?: string[]; voices?: VoiceProfile[]; knobs?: TtsKnobSpec[] };
export type CatalogProvider = { id: string; label?: string; enabled?: boolean; configured?: boolean; models?: { stt?: CatalogModel[]; llm?: CatalogModel[]; tts?: CatalogModel[] } };
export type CatalogResponse = { providers?: CatalogProvider[]; voiceInventory?: { errors?: string[] } };

export type TelephonyProvider = {
  id: string;
  name?: string;
  enabled?: boolean;
  ready?: boolean;
  phone_number?: string;
  connection_id?: string;
  account_info?: { auth_id?: string; app_id?: string };
};
export type TelephonyStatus = {
  active_provider?: string;
  active_enabled?: boolean;
  active_ready?: boolean;
  providers?: TelephonyProvider[];
  enabled_providers?: string[];
};

export const DEFAULT_TIER_LABELS: Record<string, string> = {
  low: "Economical Tier",
  medium: "Standard Regional Tier",
  premium: "Gemini 3.8 Live (Flagship)",
};

export function getVoicesForTtsProvider(providers: CatalogProvider[], provider: string, model: string, languages: string[], previous: VoiceProfile[] = []): VoiceProfile[] {
  const rows = providers.find((entry) => entry.id === provider)?.models?.tts?.find((entry) => entry.id === model)?.voices || [];
  return rows.filter((voice) => voice.selectable !== false).map((voice) => ({ ...voice,
    id: previous.find((item) => item.providerVoiceId === voice.providerVoiceId)?.id || voice.id,
    languages: voice.languages.filter((language) => !languages.length || languages.includes(language)),
  })).filter((voice) => voice.languages.length > 0);
}

export const DEFAULT_VOICE_DYNAMICS: VoiceDynamics = { speed: 1.0, pitch: 0.0, temperature: 0.7, emotion: "calm", volume: 1.0 };

// Native live voice (Gemini Live / OpenAI Realtime) exposes one delivery knob:
// speed, clamped by server/realtime/models.normalize_realtime_speed.
export const NATIVE_LIVE_KNOBS: TtsKnobSpec[] = [
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

export const FALLBACK_SPEED_KNOB: TtsKnobSpec = {
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

export function resolveModelKnobs(providers: CatalogProvider[], provider: string, model: string): TtsKnobSpec[] | null {
  const specs = providers.find((entry) => entry.id === provider)?.models?.tts?.find((entry) => entry.id === model)?.knobs;
  return Array.isArray(specs) && specs.length > 0 ? specs : null;
}

export function dynamicsValue(dynamics: VoiceDynamics | undefined, key: TtsKnobKey): number | string | undefined {
  if (!dynamics) return undefined;
  switch (key) {
    case "speed": return dynamics.speed;
    case "pitch": return dynamics.pitch;
    case "temperature": return dynamics.temperature;
    case "emotion": return dynamics.emotion;
    case "volume": return dynamics.volume;
  }
}

export function knobPatch(key: TtsKnobKey, value: number | string): Partial<VoiceDynamics> {
  switch (key) {
    case "speed": return { speed: Number(value) };
    case "pitch": return { pitch: Number(value) };
    case "temperature": return { temperature: Number(value) };
    case "emotion": return { emotion: String(value) };
    case "volume": return { volume: Number(value) };
  }
}

export function assignKnob(target: VoiceDynamics, key: TtsKnobKey, value: number | string): void {
  switch (key) {
    case "speed": target.speed = Number(value); break;
    case "pitch": target.pitch = Number(value); break;
    case "temperature": target.temperature = Number(value); break;
    case "emotion": target.emotion = String(value); break;
    case "volume": target.volume = Number(value); break;
  }
}

export function normalizeDynamicsForKnobs(dynamics: VoiceDynamics | undefined, knobs: TtsKnobSpec[]): VoiceDynamics {
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

export function speedPresetsFor(spec: TtsKnobSpec): Array<{ value: number; label: string }> {
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

export const EMPTY_EVIDENCE: ProfileEvidence = {
  sarvamModelAccess: false, sttVerified: false, ttsCatalogVerified: false,
  toolsVerified: false, capacityVerified: false, mediaFormatsVerified: false, credentialRefConfigured: false,
};

export function defaultProfileForTier(tier: ProfileTier): ComposedProfile {
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

export function normalizeProfile(profile: ComposedProfile | null | undefined, tier: ProfileTier): ComposedProfile {
  const fallback = defaultProfileForTier(tier);
  if (!profile) return fallback;
  return {
    schemaVersion: 1,
    enabled: profile.enabled === true,
    label: profile.label || DEFAULT_TIER_LABELS[tier] || tier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    webRetailRateInr: profile.webRetailRateInr ?? null,
    // Never invent a price for a saved tier: blank means "not set on the card".
    retailRateInr: profile.retailRateInr !== undefined && profile.retailRateInr !== null ? Number(profile.retailRateInr) : null,
    supplierCostInr: profile.supplierCostInr !== undefined && profile.supplierCostInr !== null ? Number(profile.supplierCostInr) : null,
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
    disabledReason: profile.disabledReason,
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

export function StatusPill({ tone, children }: { tone: "good" | "warn" | "bad" | "muted"; children: ReactNode }) {
  const style = {
    good: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    warn: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    bad: "border-rose-400/25 bg-rose-400/10 text-rose-200",
    muted: "border-surface-border-subtle bg-surface-raised text-text-muted",
  }[tone];
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${style}`}>{children}</span>;
}

export async function responseError(response: Response): Promise<string> {
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

export type ApiError = { message: string; code?: string; field?: string; status: number; details: Record<string, unknown> };

/** Structured error from a FastAPI `{detail: {error: {code, message, ...}}}` response. */
export async function parseApiError(response: Response): Promise<ApiError> {
  const payload: unknown = await response.clone().json().catch(() => null);
  let code: string | undefined;
  let field: string | undefined;
  let details: Record<string, unknown> = {};
  if (typeof payload === "object" && payload !== null) {
    const raw = payload as Record<string, unknown>;
    const detail = raw.detail ?? raw.error ?? raw;
    if (typeof detail === "object" && detail !== null) {
      const d = detail as Record<string, unknown>;
      const err = (typeof d.error === "object" && d.error !== null) ? (d.error as Record<string, unknown>) : d;
      details = err;
      code = typeof err.code === "string" ? err.code : undefined;
      field = typeof err.field === "string" ? err.field : undefined;
    }
  }
  return { message: await responseError(response), code, field, status: response.status, details };
}

/** The executable tuple whose change resets verification evidence on the server. */
export function runtimeSignature(profile: ComposedProfile | null | undefined): string {
  if (!profile) return "";
  const models = (profile.engines || []).flatMap((engine) => (engine.models || []).map((model) => [model.provider, model.model, model.apiMode]));
  return JSON.stringify([profile.stt?.provider, profile.stt?.model, profile.llm?.provider, profile.llm?.modelId, profile.llm?.apiMode, models]);
}

export function allModels(profile: ComposedProfile): ModelProfile[] {
  return (profile.engines || []).flatMap((engine) => engine.models || []);
}

export function formatInr(paise: number | undefined | null): string {
  if (paise === undefined || paise === null || !Number.isFinite(paise)) return "Not set";
  return `INR ${(paise / 100).toFixed(2)}/min`;
}

/** Plain-language next step for each readiness blocker the server reports. */
export function blockerHint(code: string, native: boolean): string {
  switch (code) {
    case "tier_native_rate_missing":
      return "Set the phone call price on this tier card and save.";
    case "provider_not_ready":
      return "Configure and enable the provider credentials on the Providers page.";
    case "model_not_approved":
      return "Approve the model in the provider catalog, or choose an approved model.";
    case "speech_voice_mismatch":
      return "Refresh provider voices, then pick a speech model whose voices cover the tier languages.";
    case "native_model_mismatch":
    case "unsupported_text_protocol":
      return "Pick a speech model that matches the selected conversation model.";
    case "profile_not_configured":
      return "Load the recommended setup, then save.";
    case "provider_registry_unavailable":
      return "The provider registry could not be read. Retry in a minute.";
    default:
      if (native) return "Native audio tiers are confirmed with a Test Studio session.";
      return "Run Verify saved setup after saving the latest changes.";
  }
}

export const PRICE_SOURCE_LABEL: Record<string, string> = {
  tier_card: "Set on this tier card",
  billing_rate_version: "From the billing rate table (no price on the tier card)",
  missing: "No price configured",
};
