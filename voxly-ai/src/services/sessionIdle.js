/**
 * Inactivity-bounded sessions (OWASP ASVS 2.7 / SOC2 "session timeout").
 *
 * The refresh cookie used to outlive any reasonable session: 30 days, silently
 * re-issued by the API client's 401 interceptor. An operator could walk away from
 * an unlocked console and come back hours later to a session that was still live.
 *
 * This module owns the *client* half of the policy — the server independently
 * refuses a refresh older than the same idle bound, so this is about telling the
 * person what is happening before it happens, not about being the enforcement
 * point.
 *
 * The bounds come from the server (`sessionPolicy` on any auth response), never
 * from a copy in this file.
 */
import { publishActivity, publishIdleWarning } from './authSessionSync';

/** Defaults only; a real deployment overwrites these from /api/auth/session-policy. */
export const DEFAULT_IDLE_TIMEOUT_MS = 30 * 60 * 1000;
export const DEFAULT_WARNING_MS = 2 * 60 * 1000;

/** Set to 0 to turn the client timer off (the server check still applies). */
const OVERRIDE_KEY = 'voxly_idle_timeout_ms';

const ACTIVITY_EVENTS = [
  'pointerdown',
  'keydown',
  'wheel',
  'touchstart',
  'focus',
  'visibilitychange',
];

function readOverride() {
  try {
    const raw = localStorage.getItem(OVERRIDE_KEY);
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? n : null;
  } catch {
    return null;
  }
}

/**
 * Shorten (never extend) the timer for local/E2E runs. A 30-minute policy cannot
 * be exercised in a test without this; the clamp keeps it from being used to
 * *relax* the policy by accident.
 */
export function setIdleTimeoutOverride(ms) {
  try {
    if (ms === null || ms === undefined) localStorage.removeItem(OVERRIDE_KEY);
    else localStorage.setItem(OVERRIDE_KEY, String(ms));
  } catch {
    /* storage blocked */
  }
}

/**
 * @param {object} opts
 * @param {number} [opts.idleTimeoutMinutes] server-authoritative idle bound
 * @param {number} [opts.absoluteMaxHours]   server-authoritative hard cap
 * @param {() => void} opts.onExpire        fired once when the idle bound is crossed
 * @param {(state) => void} opts.onState    idle/warning/active transitions
 */
export function createIdleSessionMonitor(opts = {}) {
  const {
    idleTimeoutMinutes = DEFAULT_IDLE_TIMEOUT_MS / 60000,
    absoluteMaxHours = 24,
    onExpire = () => {},
    onState = () => {},
  } = opts;

  let enabled = false;
  let disposed = false;
  let tickTimer = null;
  let lastActivityAt = Date.now();
  let sessionStartedAt = Date.now();
  let lastBroadcastAt = 0;
  let expired = false;
  let state = 'active';

  function idleLimitMs() {
    const override = readOverride();
    const base = Math.max(0, idleTimeoutMinutes) * 60_000;
    if (override === null) return base;
    return Math.min(base, override);
  }

  function absoluteLimitMs() {
    return Math.max(0, absoluteMaxHours) * 3_600_000;
  }

  function warningWindowMs() {
    const limit = idleLimitMs();
    if (limit <= 0) return 0;
    // The production warning is 2 minutes. On a shortened (test) window that would
    // swallow the whole idle period and show the countdown from the first second, so
    // scale it down to a quarter of the limit instead.
    return Math.min(DEFAULT_WARNING_MS, Math.max(1500, Math.floor(limit * 0.25)));
  }

  function remainingMs() {
    const limit = idleLimitMs();
    if (limit <= 0) return Number.POSITIVE_INFINITY;
    return Math.max(0, limit - (Date.now() - lastActivityAt));
  }

  function emit(next) {
    if (state === next) return;
    state = next;
    onState({
      state: next,
      remainingMs: remainingMs(),
      warningMs: warningWindowMs(),
      idleTimeoutMinutes,
      absoluteMaxHours,
    });
  }

  /**
   * Mirror the live window onto <html data-*> so support (and an end-to-end test) can
   * see the countdown instead of guessing at it. Without it the only observable sign of
   * the policy is the modal, which appears in the last two minutes.
   */
  function publish() {
    if (typeof document === 'undefined') return;
    try {
      const root = document.documentElement;
      root.dataset.voxlyIdleState = state;
      root.dataset.voxlyIdleRunning = enabled ? '1' : '0';
      root.dataset.voxlyIdleRemainingMs = String(Math.max(0, Math.round(remainingMs())));
      root.dataset.voxlyIdleLimitMs = String(idleLimitMs());
    } catch {
      /* ignore */
    }
  }

  function expire(reason) {
    if (expired || disposed) return;
    expired = true;
    publishIdleWarning(reason);
    emit('expired');
    onExpire(reason);
  }

  function evaluate() {
    if (disposed || !enabled) return;
    const now = Date.now();
    if (absoluteLimitMs() > 0 && now - sessionStartedAt >= absoluteLimitMs()) {
      state = 'expired';
      publish();
      expire('session_absolute_max');
      return;
    }
    const limit = idleLimitMs();
    if (limit <= 0) {
      emit('active');
      publish();
      return;
    }
    const idleFor = now - lastActivityAt;
    if (idleFor >= limit) {
      state = 'expired';
      publish();
      expire('session_idle');
      return;
    }
    if (idleFor >= Math.max(0, limit - warningWindowMs())) emit('warning');
    else emit('active');
    publish();
  }

  /** Register human activity. Throttled so a mouse-move storm is not work. */
  function noteActivity({ broadcast = true } = {}) {
    const now = Date.now();
    lastActivityAt = now;
    if (broadcast && now - lastBroadcastAt > 5000) {
      lastBroadcastAt = now;
      publishActivity();
    }
    if (expired) return;
    evaluate();
  }

  function onActivityEvent(ev) {
    if (ev?.type === 'visibilitychange' && document.visibilityState === 'hidden') return;
    noteActivity();
  }

  return {
    start() {
      if (enabled || disposed) return;
      enabled = true;
      lastActivityAt = Date.now();
      sessionStartedAt = Date.now();
      expired = false;
      ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, onActivityEvent, { passive: true }));
      evaluate();
      const timer = setInterval(evaluate, 1000);
      tickTimer = timer;
    },
    stop() {
      enabled = false;
      if (tickTimer) {
        clearInterval(tickTimer);
        tickTimer = null;
      }
      ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, onActivityEvent));
      publish();
    },
    dispose() {
      this.stop();
      disposed = true;
    },
    /** Adopt a peer tab's activity timestamp instead of starting idle from zero. */
    syncFromPeer(at) {
      if (!at) return;
      if (at > lastActivityAt) lastActivityAt = at;
      evaluate();
    },
    /** Countdown still running after "Stay signed in": extend the window. */
    extend() {
      expired = false;
      lastActivityAt = Date.now();
      evaluate();
    },
    /** Sign in happened: restart both the idle and the absolute clock. */
    resetSession() {
      lastActivityAt = Date.now();
      sessionStartedAt = Date.now();
      expired = false;
      evaluate();
    },
    noteActivity,
    get remainingMs() {
      return remainingMs();
    },
    get isWarning() {
      return state === 'warning';
    },
    get enabled() {
      return enabled;
    },
  };
}