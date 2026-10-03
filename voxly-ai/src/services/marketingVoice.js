/**
 * Playback for the marketing voice samples.
 *
 * These clips are rendered by the live speech model that answers real calls
 * (`gemini-3.8-live`, see scripts/record_marketing_voice_samples.py), so the demo
 * audio and the product audio are the same voice. That is the whole point: the page
 * previously spoke with `window.speechSynthesis`, which is the *browser's* voice, so
 * the thing a visitor heard was evidence against the claim being made.
 *
 * Playback runs through `voiceAgent.playAudioClip`, which routes the clip through the
 * Web Audio analyser — that is what drives the 3D mascot's mouth and the waveform here,
 * so the visuals follow the actual audio instead of an animation on a timer.
 */
import { VOICE_SAMPLES } from '../data/voiceSamples';
import { voiceAgent } from './voiceAgent';

export { VOICE_SAMPLES };

/**
 * Reticle signal, when the dev SDK is present.
 *
 * "The clip is playing" is a claim about audio, and a screenshot cannot show it. The
 * analyser level crossing a threshold is the app's own evidence that real samples are
 * being decoded and played, which is what makes the demo verifiable instead of
 * asserted. A no-op in production.
 */
function emitSignal(name, data) {
  if (typeof window === 'undefined') return;
  try {
    // `@reticlehq/browser` parks its singleton on globalThis.__reticleInstance.
    const instance =
      window.reticle || window.__reticle || window.__reticleInstance || null;
    if (instance && typeof instance.signal === 'function') instance.signal(name, data);
  } catch {
    /* verification tooling absent — not an error */
  }
}

export function getVoiceSample(id) {
  return VOICE_SAMPLES.find((s) => s.id === id) || null;
}

export function sampleIndustries() {
  return VOICE_SAMPLES.map((s) => ({
    id: s.id,
    industry: s.industry,
    label: s.label,
    durationSeconds: s.durationSeconds,
  }));
}

/**
 * Speak a sample. `onLevel` receives 0..1 amplitude from the analyser so callers can
 * animate to the real signal.
 *
 * Returns a stop function.
 */
export function playVoiceSample(sample, { onLevel, onEnd, onStart } = {}) {
  if (!sample?.url) {
    onEnd?.();
    return () => {};
  }
  let raf = 0;
  let stopped = false;
  let announced = false;
  // Create the audio graph BEFORE reading the analyser: on the first play it does not
  // exist yet, and a null analyser means a waveform frozen at its idle shape — the
  // visual would look like "playing" while proving nothing.
  voiceAgent.ensureAudioContext();
  const analyser = voiceAgent.getAnalyser();
  const bytes = new Uint8Array(analyser ? analyser.frequencyBinCount : 0);

  const pump = () => {
    if (stopped) return;
    if (analyser) {
      analyser.getByteTimeDomainData(bytes);
      // RMS around the 128 midpoint: silent is 0, speech peaks near 1.
      let sum = 0;
      for (let i = 0; i < bytes.length; i += 1) {
        const v = (bytes[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / Math.max(1, bytes.length));
      const level = Math.min(1, rms * 3.2);
      onLevel?.(level);
      if (!announced && level > 0.06) {
        announced = true;
        emitSignal('voxly:voice-sample-audible', { id: sample.id, voice: sample.voice, url: sample.url });
      }
    }
    raf = requestAnimationFrame(pump);
  };

  voiceAgent.playAudioClip(
    sample.url,
    () => {
      stopped = true;
      cancelAnimationFrame(raf);
      onLevel?.(0);
      emitSignal('voxly:voice-sample-ended', { id: sample.id });
      onEnd?.();
    },
    () => {
      onLevel?.(0.15);
      pump();
      emitSignal('voxly:voice-sample-started', { id: sample.id, url: sample.url });
      onStart?.();
    },
    { playSoundEffect: false }
  );

  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    voiceAgent.stopTTS();
  };
}

/**
 * Speak the same line with the browser's built-in voice, for the side-by-side
 * comparison. This is deliberately the *old* behaviour, kept as the "before" in the
 * A/B: it is the voice most automated phone systems ship, and hearing it next to the
 * real pipeline is more persuasive than describing the difference.
 */
export function playBrowserVoiceSample(sample, { onEnd } = {}) {
  if (!sample?.text) {
    onEnd?.();
    return;
  }
  voiceAgent.playTTS(sample.text, () => onEnd?.(), undefined, { soundType: 'chime' });
}

/** Total sample time in the manifest, for the "what you just heard" caption. */
export function sampleDurationLabel(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `0:${String(s).padStart(2, '0')}`;
}