/**
 * Mic uplink gating — half-duplex during agent TTS (prevents speaker→mic feedback loops).
 * Ported from client/app.js RMS gate with stricter playback mute.
 */

/** RMS below this while agent speaks is treated as speaker echo (float 0–1). */
export const RMS_SPEAKING_THRESHOLD = 0.012;

/** Block mic uplink for this long after TTS ends (room reverb tail). */
export const PLAYBACK_TAIL_MS = 900;

/** Minimum time after TTS starts before barge-in is allowed. */
export const BARGE_MIN_AFTER_SPEAK_MS = 700;

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
export function shouldSendMicToStt(state: MicGateState, now: number, rms: number): boolean {
  if (state.awaitingUserAfterBarge) return true;
  if (state.agentSpeaking) {
    return rms >= RMS_SPEAKING_THRESHOLD * 2.5;
  }
  if (now < state.speakCooldownUntil) {
    return rms >= RMS_SPEAKING_THRESHOLD * 1.5;
  }
  return true;
}

/** True when VAD/partial barge-in is allowed (not echo from speakers). */
export function shouldAllowBargeIn(state: MicGateState, now: number): boolean {
  if (!state.agentSpeaking && !state.brainStreaming) return false;
  if (state.agentSpeaking && state.speakStartedAt > 0) {
    if (now - state.speakStartedAt < BARGE_MIN_AFTER_SPEAK_MS) return false;
  }
  if (now < state.speakCooldownUntil) return false;
  return true;
}
