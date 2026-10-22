/** Gate STT finals before sending to brain — reduces echo fragments and junk turns. */

import { wordCount } from "@/lib/early-tts";

const INDIC_SCRIPT = /[\u0900-\u097F\u0C00-\u0C7F]/;

/** Count words; Indic scripts often lack spaces — use char clusters as fallback. */
export function effectiveWordCount(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  const spaced = wordCount(trimmed);
  if (spaced >= 2) return spaced;
  if (INDIC_SCRIPT.test(trimmed)) {
    const clusters = trimmed.replace(/\s+/g, "").length;
    if (clusters >= 6) return Math.max(2, Math.ceil(clusters / 4));
  }
  return spaced;
}

export type TranscriptGateOpts = {
  /** After explicit barge-in — allow shorter caller utterances. */
  afterBarge?: boolean;
  /** From queue during agent TTS — require more substance. */
  fromSpeechQueue?: boolean;
};

/**
 * True when a final transcript is worth a brain turn.
 * Blocks STT debris like "and that will plot." right after agent speech.
 */
export function isSubstantiveTranscript(text: string, opts?: TranscriptGateOpts): boolean {
  const t = text.trim();
  if (!t) return false;
  const words = effectiveWordCount(t);
  const chars = t.replace(/\s+/g, "").length;

  if (opts?.afterBarge) {
    return words >= 1 && chars >= 3;
  }
  if (opts?.fromSpeechQueue) {
    return words >= 3 || chars >= 12;
  }
  return words >= 2 || chars >= 8;
}

const VALID_SHORT_REPLY =
  /^(?:ok|okay|yes|no|sure|thanks|thank you|got it|sare|hmm|mm|aha|అవును|సరే|ठीक|हाँ)\.?$/i;
const MIDWORD_STUMP = /\b(?:lak|cro|rupee|from|with|and|or|the|we|i|to|for|a|an)\.?$/i;

/** Very short assistant text that looks cut off mid-thought. */
export function looksIncompleteReply(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  if (VALID_SHORT_REPLY.test(t)) return false;
  // Token/barge crumbs that end with forced "." still count as incomplete.
  if (MIDWORD_STUMP.test(t) && t.length < 100) {
    if (t.length < 24 || /\b(?:lak|cro)\.?$/i.test(t)) return true;
  }
  if (t.length >= 40) return false;
  if (/[.!?।]\s*$/.test(t)) return false;
  if (effectiveWordCount(t) >= 8) return false;
  return true;
}
