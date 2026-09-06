/**
 * Live session guard rules — pure functions for barge-in / think-cancel.
 * Keep in sync with server/tests/test_live_barge_policy.py
 */
(function (root) {
  const BARGE_DEBOUNCE_MS = 800;
  const THINK_CANCEL_MIN_MS = 350;
  const THINK_CANCEL_MIN_WORDS = 2;
  const SPEAK_BARGE_MIN_WORDS = 3;
  const BARGE_HOLD_MS = 200;

  function shouldDebounceBargeIn(state, now) {
    return (
      state.bargeHandledTurn === state.turnN &&
      now - (state.lastBargeInAt || 0) < BARGE_DEBOUNCE_MS
    );
  }

  function shouldThinkCancel(state) {
    return (
      state.busy &&
      state.brainStreaming &&
      !state.agentSpeaking &&
      state.elapsedMs > THINK_CANCEL_MIN_MS &&
      state.words >= THINK_CANCEL_MIN_WORDS
    );
  }

  function shouldBargeWhileSpeaking(state, now) {
    if (!state.agentSpeaking) return false;
    const minWords = state.minWords ?? SPEAK_BARGE_MIN_WORDS;
    const requireVad = state.requireVad !== false;
    if (state.words < minWords) return false;
    if (requireVad && !state.sawVadStart) return false;
    const holdMs = state.holdMs ?? BARGE_HOLD_MS;
    const vadStartedAt = state.vadStartedAt || 0;
    if (vadStartedAt > 0 && now - vadStartedAt < holdMs) return false;
    return now > (state.bargeCooldownUntil || 0);
  }

  root.LiveGuards = {
    BARGE_DEBOUNCE_MS,
    THINK_CANCEL_MIN_MS,
    THINK_CANCEL_MIN_WORDS,
    SPEAK_BARGE_MIN_WORDS,
    BARGE_HOLD_MS,
    shouldDebounceBargeIn,
    shouldThinkCancel,
    shouldBargeWhileSpeaking,
  };
})(typeof window !== "undefined" ? window : globalThis);
