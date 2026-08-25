/** Barge-in policy — parity with client/live-guards.js */
export const BARGE_DEBOUNCE_MS = 800;
export const THINK_CANCEL_MIN_MS = 350;
export const THINK_CANCEL_MIN_WORDS = 2;
export const SPEAK_BARGE_MIN_WORDS = 3;

export interface BargeState {
  bargeHandledTurn: number;
  lastBargeInAt: number;
  busy: boolean;
  brainStreaming: boolean;
  agentSpeaking: boolean;
  elapsedMs: number;
  words: number;
  sawVadStart: boolean;
  bargeCooldownUntil: number;
  turnN: number;
  minWords?: number;
  requireVad?: boolean;
}

export function shouldDebounceBargeIn(state: BargeState, now: number): boolean {
  return state.bargeHandledTurn === state.turnN && now - state.lastBargeInAt < BARGE_DEBOUNCE_MS;
}

export function shouldThinkCancel(state: BargeState): boolean {
  return (
    state.busy &&
    state.brainStreaming &&
    !state.agentSpeaking &&
    state.elapsedMs > THINK_CANCEL_MIN_MS &&
    state.words >= THINK_CANCEL_MIN_WORDS
  );
}

export function shouldBargeWhileSpeaking(state: BargeState, now: number): boolean {
  if (!state.agentSpeaking) return false;
  const minWords = state.minWords ?? SPEAK_BARGE_MIN_WORDS;
  const requireVad = state.requireVad !== false;
  if (state.words < minWords) return false;
  if (requireVad && !state.sawVadStart) return false;
  return now > state.bargeCooldownUntil;
}
