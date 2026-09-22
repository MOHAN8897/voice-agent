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

export const REALTIME_VOICES: { id: string; label: string }[] = [
  { id: "marin", label: "Marin" },
  { id: "cedar", label: "Cedar" },
  { id: "alloy", label: "Alloy" },
  { id: "ash", label: "Ash" },
  { id: "ballad", label: "Ballad" },
  { id: "coral", label: "Coral" },
  { id: "echo", label: "Echo" },
  { id: "sage", label: "Sage" },
  { id: "shimmer", label: "Shimmer" },
  { id: "verse", label: "Verse" },
];

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
