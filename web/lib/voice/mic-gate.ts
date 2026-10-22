/**
 * Mic uplink gating — half-duplex during agent TTS (prevents speaker→mic feedback loops).
 */

import type { VoiceAudioProfile } from "@/lib/voice/mobile-audio";
import { resolveVoiceAudioProfile } from "@/lib/voice/mobile-audio";

/** RMS below this while agent speaks is treated as speaker echo (float 0–1). */
export const RMS_SPEAKING_THRESHOLD = 0.012;

/** Block mic uplink for this long after TTS ends (room reverb tail). */
export const PLAYBACK_TAIL_MS = 900;

/** Minimum time after TTS starts before barge-in is allowed. */
export const BARGE_MIN_AFTER_SPEAK_MS = 700;

export type MicGateConfig = {
  rmsSpeakingThreshold: number;
  playbackTailMs: number;
  bargeMinAfterSpeakMs: number;
  speakingRmsMultiplier: number;
  cooldownRmsMultiplier: number;
};

export function micGateConfig(profile?: VoiceAudioProfile): MicGateConfig {
  const p = profile ?? resolveVoiceAudioProfile();
  return {
    rmsSpeakingThreshold: RMS_SPEAKING_THRESHOLD,
    playbackTailMs: p.playbackTailMs,
    bargeMinAfterSpeakMs: p.bargeMinAfterSpeakMs,
    speakingRmsMultiplier: p.speakingRmsMultiplier,
    cooldownRmsMultiplier: p.cooldownRmsMultiplier,
  };
}

export function pcmRms16(samples: Int16Array): number {
  if (!samples.length) return 0;
  let sum = 0;
  const step = 4;
  const n = Math.ceil(samples.length / step);
  for (let i = 0; i < samples.length; i += step) {
    const v = samples[i] / 32768;
    sum += v * v;
  }
  return Math.sqrt(sum / Math.max(1, n));
}

export type MicGateState = {
  agentSpeaking: boolean;
  brainStreaming: boolean;
  awaitingUserAfterBarge: boolean;
  speakCooldownUntil: number;
  speakStartedAt: number;
};

/** True when mic PCM should be sent to STT. */
export function shouldSendMicToStt(
  state: MicGateState,
  now: number,
  rms: number,
  config: MicGateConfig = micGateConfig()
): boolean {
  if (state.awaitingUserAfterBarge) return true;
  const base = config.rmsSpeakingThreshold;
  if (state.agentSpeaking) {
    return rms >= base * config.speakingRmsMultiplier;
  }
  if (now < state.speakCooldownUntil) {
    return rms >= base * config.cooldownRmsMultiplier;
  }
  return true;
}

export function bargeRmsFloor(config: MicGateConfig): number {
  return config.rmsSpeakingThreshold * config.speakingRmsMultiplier;
}

/** During agent speech, partial barge must exceed RMS floor (not just STT text). */
export function rmsAllowsSpeakBarge(rms: number, config: MicGateConfig): boolean {  return rms >= bargeRmsFloor(config);
}

/** True when VAD/partial barge-in is allowed (not echo from speakers). */
export function shouldAllowBargeIn(
  state: MicGateState,
  now: number,
  config: MicGateConfig = micGateConfig()
): boolean {
  if (!state.agentSpeaking && !state.brainStreaming) return false;
  if (state.agentSpeaking && state.speakStartedAt > 0) {
    if (now - state.speakStartedAt < config.bargeMinAfterSpeakMs) return false;
  }
  if (now < state.speakCooldownUntil) return false;
  return true;
}