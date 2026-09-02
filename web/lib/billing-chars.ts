/**
 * Unicode code-point count for TTS billing (Sarvam: per character including Telugu).
 * Use Array.from — not .length — so astral symbols count as one char, not two UTF-16 units.
 */
export function billingCharCount(text: string | null | undefined): number {
  if (!text) return 0;
  return Array.from(text).length;
}
