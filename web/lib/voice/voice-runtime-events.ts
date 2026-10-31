/** Notify live TTS clients when Test Studio voice runtime changes. */
type VoiceRuntimeListener = (speaker: string) => void;

const listeners = new Set<VoiceRuntimeListener>();

export function onTestStudioVoiceSaved(listener: VoiceRuntimeListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function notifyTestStudioVoiceSaved(speaker: string) {
  for (const fn of listeners) fn(speaker);
}
