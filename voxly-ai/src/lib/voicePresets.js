/** Subscriber-facing voice styles (no vendor/stack names in UI). */
export const VOICE_PRESETS = [
  { id: 'warm', label: 'Warm & welcoming', speed: 1.0, pitch: 0 },
  { id: 'neutral', label: 'Clear & neutral', speed: 1.0, pitch: 0 },
  { id: 'energetic', label: 'Upbeat & energetic', speed: 1.08, pitch: 0.05 },
];

export const LANGUAGE_OPTIONS = [
  { label: 'English (India)', code: 'en-IN' },
  { label: 'English (UK)', code: 'en-GB' },
  { label: 'Telugu', code: 'te-IN' },
  { label: 'Hindi', code: 'hi-IN' },
  { label: 'Tamil', code: 'ta-IN' },
  { label: 'Kannada', code: 'kn-IN' },
];

export function voiceFromPreset(presetId, agentName = '') {
  const preset = VOICE_PRESETS.find((p) => p.id === presetId) || VOICE_PRESETS[0];
  return {
    provider: 'default',
    voiceId: preset.id,
    voiceName: preset.label,
    speed: preset.speed,
    pitch: preset.pitch,
    stability: 0.75,
    displayName: agentName || preset.label,
  };
}

export function languagesFromCode(code) {
  return code ? [code] : ['en-IN'];
}
