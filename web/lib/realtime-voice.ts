export const DEFAULT_REALTIME_VOICE = "marin";
export const DEFAULT_REALTIME_TURN_DETECTION = "semantic_vad";
export const DEFAULT_REALTIME_VAD_EAGERNESS = "high";
export const DEFAULT_REALTIME_NOISE_REDUCTION = "far_field";
export const DEFAULT_REALTIME_SPEED = 1;
export const DEFAULT_REALTIME_SILENCE_MS = 250;

export const REALTIME_MODEL_IDS = [
  "gpt-realtime-2.1-mini",
  "gpt-realtime-2.1",
  "gpt-realtime-2",
] as const;

export const GEMINI_LIVE_MODEL_IDS = [
  "gemini-3.8-live",
  "gemini-2.5-flash-native-audio-latest",
] as const;

export function isGeminiLiveVoiceModel(slug: string | undefined): boolean {
  const id = String(slug || "").trim().toLowerCase();
  if (!id) return false;
  if ((GEMINI_LIVE_MODEL_IDS as readonly string[]).includes(id)) return true;
  return id.startsWith("gemini-") && (id.endsWith("-live") || id.includes("native-audio"));
}

export function isRealtimeSpeechToSpeechModel(slug: string | undefined): boolean {
  const id = String(slug || "").trim();
  return id.startsWith("gpt-realtime") || isGeminiLiveVoiceModel(id);
}

export type RealtimeVoiceOption = {
  id: string;
  label: string;
  gender: string;
  tone: string;
  geminiVoice: string;
  geminiGender: string;
};

/** Display metadata — keep in sync with server/services/saas/voice_catalog.py */
export const REALTIME_VOICE_OPTIONS: RealtimeVoiceOption[] = [
  { id: "marin", label: "Marin", gender: "female", tone: "Warm & clear", geminiVoice: "Puck", geminiGender: "male" },
  { id: "cedar", label: "Cedar", gender: "male", tone: "Calm & steady", geminiVoice: "Charon", geminiGender: "male" },
  { id: "alloy", label: "Alloy", gender: "neutral", tone: "Balanced", geminiVoice: "Kore", geminiGender: "female" },
  { id: "ash", label: "Ash", gender: "male", tone: "Soft", geminiVoice: "Aoede", geminiGender: "female" },
  { id: "ballad", label: "Ballad", gender: "male", tone: "Expressive", geminiVoice: "Zephyr", geminiGender: "female" },
  { id: "coral", label: "Coral", gender: "female", tone: "Friendly", geminiVoice: "Aoede", geminiGender: "female" },
  { id: "echo", label: "Echo", gender: "male", tone: "Bright", geminiVoice: "Fenrir", geminiGender: "male" },
  { id: "sage", label: "Sage", gender: "female", tone: "Professional", geminiVoice: "Orus", geminiGender: "male" },
  { id: "shimmer", label: "Shimmer", gender: "female", tone: "Light", geminiVoice: "Leda", geminiGender: "female" },
  { id: "verse", label: "Verse", gender: "male", tone: "Crisp", geminiVoice: "Puck", geminiGender: "male" },
];

export const REALTIME_VOICES: { id: string; label: string }[] = REALTIME_VOICE_OPTIONS.map((v) => ({
  id: v.id,
  label: v.label,
}));

export function realtimeVoiceOptionLabel(
  voiceId: string | undefined,
  opts?: { geminiLive?: boolean }
): string {
  const id = normalizeRealtimeVoice(voiceId);
  const row = REALTIME_VOICE_OPTIONS.find((v) => v.id === id);
  if (!row) return id;
  const gender = opts?.geminiLive ? row.geminiGender : row.gender;
  const gTag = gender && gender !== "neutral" ? ` · ${gender}` : "";
  if (opts?.geminiLive) {
    return `${row.label} → Gemini ${row.geminiVoice}${gTag}`;
  }
  return `${row.label}${gTag}`;
}

export const REALTIME_TURN_DETECTION: { id: string; label: string }[] = [
  { id: "semantic_vad", label: "Semantic VAD (recommended)" },
  { id: "server_vad", label: "Server VAD (silence)" },
];

export const REALTIME_VAD_EAGERNESS: { id: string; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "low", label: "Low — wait longer" },
  { id: "medium", label: "Medium" },
  { id: "high", label: "High — jump in faster" },
];

export const REALTIME_NOISE_REDUCTION: { id: string; label: string }[] = [
  { id: "far_field", label: "Far field (phone / PSTN)" },
  { id: "near_field", label: "Near field (headset)" },
  { id: "off", label: "Off" },
];

export function isTelephonyMode(mode: string | undefined): boolean {
  return mode === "pstn" || mode === "pstn_realtime";
}

export function isRealtimePstnMode(mode: string | undefined): boolean {
  return mode === "pstn_realtime";
}

export function normalizeRealtimeVoice(voice: string | undefined): string {
  const slug = String(voice || "").trim().toLowerCase();
  return REALTIME_VOICES.some((v) => v.id === slug) ? slug : DEFAULT_REALTIME_VOICE;
}

export function normalizeRealtimeTurnDetection(kind: string | undefined): string {
  const slug = String(kind || "").trim().toLowerCase();
  return REALTIME_TURN_DETECTION.some((v) => v.id === slug) ? slug : DEFAULT_REALTIME_TURN_DETECTION;
}

export function normalizeRealtimeVadEagerness(kind: string | undefined): string {
  const slug = String(kind || "").trim().toLowerCase();
  return REALTIME_VAD_EAGERNESS.some((v) => v.id === slug) ? slug : DEFAULT_REALTIME_VAD_EAGERNESS;
}

export function normalizeRealtimeNoiseReduction(kind: string | undefined): string {
  const slug = String(kind || "").trim().toLowerCase();
  return REALTIME_NOISE_REDUCTION.some((v) => v.id === slug) ? slug : DEFAULT_REALTIME_NOISE_REDUCTION;
}

export function normalizeRealtimeSpeed(value: number | string | undefined): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_REALTIME_SPEED;
  return Math.min(1.5, Math.max(0.25, Math.round(n * 100) / 100));
}

export function normalizeRealtimeSilenceMs(value: number | string | undefined): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_REALTIME_SILENCE_MS;
  return Math.min(2000, Math.max(200, Math.round(n)));
}
