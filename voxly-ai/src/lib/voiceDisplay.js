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

/**
 * Customer-facing tiers for the voice picker.
 *
 * The picker used to be grouped by supplier ("OpenAI (phone default)", "Gemini Live").
 * A tenant does not care which vendor is behind the voice, and naming them invites
 * exactly the conversation the product should not be having — comparing our per-minute
 * rate against their own API bill. Grouping by how the voice *sounds* keeps the choice
 * a buying decision ("warm and reassuring" for a clinic) instead of an infrastructure
 * one, and leaves the supplier as an implementation detail.
 */
const TIER_ONE_IDS = new Set(['marin', 'cedar', 'sage', 'jade', 'amber', 'coral', 'ember', 'nova']);

const TONE_TO_TIER = [
  [/warm|reassur|calm|soothing|gentle|empathetic|caring|friendly/i, 'customer-care'],
  [/formal|profession|authoritative|corporate|business|executive|precise/i, 'formal'],
  [/bright|energetic|upbeat|excited|enthusiast|cheerful|playful/i, 'energetic'],
];

export function voiceTierLabel(voice) {
  if (!voice) return 'Standard';
  const id = String(voice.id || '').toLowerCase();
  const haystack = `${voice.id || ''} ${voice.label || ''} ${voice.tone || ''}`;
  for (const [pattern, tier] of TONE_TO_TIER) {
    if (pattern.test(haystack)) {
      return tier === 'customer-care'
        ? 'Expressive Customer Care'
        : tier === 'formal'
          ? 'Professional & Formal'
          : 'Bright & Energetic';
    }
  }
  if (TIER_ONE_IDS.has(id)) return 'Ultra-Realistic Conversational (Tier 1)';
  return 'Ultra-Realistic Conversational (Tier 1)';
}

/** Voices bucketed by tier, in a stable display order. No supplier names. */
export function groupVoicesByTier(voices) {
  const list = Array.isArray(voices) ? voices : [];
  const order = [
    'Ultra-Realistic Conversational (Tier 1)',
    'Expressive Customer Care',
    'Professional & Formal',
    'Bright & Energetic',
  ];
  const buckets = new Map(order.map((name) => [name, []]));
  for (const voice of list) {
    const tier = voiceTierLabel(voice);
    if (!buckets.has(tier)) buckets.set(tier, []);
    buckets.get(tier).push(voice);
  }
  return order
    .map((label) => ({ label, voices: buckets.get(label) || [] }))
    .filter((group) => group.voices.length > 0);
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