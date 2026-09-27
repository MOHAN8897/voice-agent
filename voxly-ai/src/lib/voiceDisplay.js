/** Labels for phone AI voices returned by /api/telephony/voice-options */

export function formatPhoneVoiceLabel(v) {
  if (!v) return 'Voice';
  const parts = [v.label || v.id];
  if (v.gender && v.gender !== 'neutral') {
    parts.push(v.gender === 'male' ? 'Male' : v.gender === 'female' ? 'Female' : v.gender);
  }
  if (v.tone) parts.push(v.tone);
  return parts.join(' · ');
}

export function groupPhoneVoices(voices) {
  const list = Array.isArray(voices) ? voices : [];
  const openai = list.filter((v) => (v.provider || 'openai') === 'openai');
  const gemini = list.filter((v) => v.provider === 'gemini');
  return { openai, gemini, all: list };
}

export function isUuid(value) {
  return (
    typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
  );
}
