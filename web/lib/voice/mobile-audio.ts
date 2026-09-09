/** Mobile audio profiles — handset (earpiece) vs speakerphone vs headphones. */

export type MobileAudioMode = "handset" | "speakerphone";

export type VoiceAudioProfile = {
  isMobile: boolean;
  headphones: boolean;
  /** Set on mobile when not using headphones. */
  mobileMode?: MobileAudioMode;
  playbackTailMs: number;
  bargeMinAfterSpeakMs: number;
  speakingRmsMultiplier: number;
  cooldownRmsMultiplier: number;
  bargeMinWordsBonus: number;
  ignoreVadDuringAgentSpeech: boolean;
  defaultSttSilenceMs: number;
  defaultSttThreshold: number;
  bargeHoldMs: number;
  thinkCancelMinWords: number;
};

const MOBILE_UA =
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|Tablet/i;

export function isMobileLikeDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (MOBILE_UA.test(ua)) return true;
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(max-width: 768px) and (pointer: coarse)").matches;
  }
  return false;
}

/** Map Test Studio voice preset → mic-gate profile on mobile. */
export function mobileModeFromPreset(presetId?: string | null): MobileAudioMode {
  const id = String(presetId || "").trim().toLowerCase();
  if (id === "speakerphone" || id === "mobile_speakerphone") return "speakerphone";
  return "handset";
}

const DESKTOP_OPEN: VoiceAudioProfile = {
  isMobile: false,
  headphones: false,
  playbackTailMs: 900,
  bargeMinAfterSpeakMs: 700,
  speakingRmsMultiplier: 2.5,
  cooldownRmsMultiplier: 1.5,
  bargeMinWordsBonus: 0,
  ignoreVadDuringAgentSpeech: false,
  defaultSttSilenceMs: 500,
  defaultSttThreshold: 0.3,
  bargeHoldMs: 200,
  thinkCancelMinWords: 2,
};

const HEADPHONES_RELAXED: VoiceAudioProfile = {
  isMobile: false,
  headphones: true,
  playbackTailMs: 550,
  bargeMinAfterSpeakMs: 450,
  speakingRmsMultiplier: 2.0,
  cooldownRmsMultiplier: 1.25,
  bargeMinWordsBonus: 0,
  ignoreVadDuringAgentSpeech: false,
  defaultSttSilenceMs: 500,
  defaultSttThreshold: 0.3,
  bargeHoldMs: 180,
  thinkCancelMinWords: 2,
};

/** Phone held to ear — moderate echo gate, responsive barge-in + VAD. */
const MOBILE_HANDSET: VoiceAudioProfile = {
  isMobile: true,
  headphones: false,
  mobileMode: "handset",
  playbackTailMs: 1000,
  bargeMinAfterSpeakMs: 850,
  speakingRmsMultiplier: 2.8,
  cooldownRmsMultiplier: 1.7,
  bargeMinWordsBonus: 1,
  ignoreVadDuringAgentSpeech: false,
  defaultSttSilenceMs: 550,
  defaultSttThreshold: 0.31,
  bargeHoldMs: 220,
  thinkCancelMinWords: 3,
};

/** Loudspeaker on — strict echo gate (previous default for all mobile). */
const MOBILE_SPEAKERPHONE: VoiceAudioProfile = {
  isMobile: true,
  headphones: false,
  mobileMode: "speakerphone",
  playbackTailMs: 1400,
  bargeMinAfterSpeakMs: 1100,
  speakingRmsMultiplier: 3.5,
  cooldownRmsMultiplier: 2.2,
  bargeMinWordsBonus: 2,
  ignoreVadDuringAgentSpeech: true,
  defaultSttSilenceMs: 650,
  defaultSttThreshold: 0.34,
  bargeHoldMs: 300,
  thinkCancelMinWords: 3,
};

export function resolveVoiceAudioProfile(opts?: {
  headphones?: boolean;
  mobileMode?: MobileAudioMode;
}): VoiceAudioProfile {
  const isMobile = isMobileLikeDevice();
  const headphones = Boolean(opts?.headphones);
  if (headphones) {
    return { ...HEADPHONES_RELAXED, isMobile, headphones: true };
  }
  const mode = opts?.mobileMode;
  if (mode === "speakerphone") {
    return { ...MOBILE_SPEAKERPHONE, isMobile: isMobile || Boolean(mode), headphones: false };
  }
  if (mode === "handset") {
    return { ...MOBILE_HANDSET, isMobile: isMobile || Boolean(mode), headphones: false };
  }
  if (!isMobile) {
    return { ...DESKTOP_OPEN, isMobile: false, headphones: false };
  }
  return { ...MOBILE_HANDSET, isMobile: true, headphones: false };
}

/** @deprecated use resolveVoiceAudioProfile */
export function mobileAudioProfile(): VoiceAudioProfile {
  return resolveVoiceAudioProfile();
}

export function profileSummary(profile: VoiceAudioProfile): string {
  if (profile.headphones) return "headphones — relaxed echo gate";
  if (profile.isMobile && profile.mobileMode === "speakerphone") {
    return "mobile speakerphone — strict echo gate";
  }
  if (profile.isMobile) return "mobile handset — direct mic, balanced barge/VAD";
  return "desktop open mic";
}
