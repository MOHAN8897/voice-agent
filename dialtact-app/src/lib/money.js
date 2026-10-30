/**
 * One money and time formatter for the console. India-first: rupees are the
 * primary figure everywhere; dollars appear only as a secondary figure where a
 * screen already showed them.
 *
 *   formatInr(1234.5)                 → "₹1,234.50"
 *   formatInr(123456)                 → "₹1,23,456"
 *   walletAmounts(wallet).primary     → "₹2,000"   (.secondary → "$20.91")
 */

const DEFAULT_FX = 95.64;

export function formatInr(value, { whole = false, compact = false } = {}) {
  const n = Number(value) || 0;
  if (compact && Math.abs(n) >= 100000) {
    return `₹${(n / 100000).toLocaleString('en-IN', { maximumFractionDigits: 1 })}L`;
  }
  const digits = whole || Number.isInteger(n) ? 0 : 2;
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function formatUsd(value) {
  const n = Number(value) || 0;
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Paise (integer) → "₹x". */
export function formatPaise(paise, options) {
  return formatInr((Number(paise) || 0) / 100, options);
}

/**
 * Wallet balance in both currencies. A wallet funded in rupees shows rupees; a
 * dollar-only wallet is converted at the server's FX rate for the rupee figure.
 */
export function walletAmounts(wallet) {
  const fx = Number(wallet?.fxRateInr) || DEFAULT_FX;
  const inrRaw = Number(wallet?.balanceInr) || 0;
  const usdRaw = Number(wallet?.balanceUsd) || 0;
  const inr = inrRaw > 0 ? inrRaw : usdRaw > 0 ? usdRaw * fx : 0;
  const usd = usdRaw > 0 ? usdRaw : inrRaw > 0 ? inrRaw / fx : 0;
  return {
    inr,
    usd,
    isEmpty: inrRaw <= 0 && usdRaw <= 0,
    primary: formatInr(Math.round(inr * 100) / 100),
    secondary: formatUsd(usd),
  };
}

/** Seconds → "2:14" (or "1:02:14") for live timers. */
export function formatClock(totalSeconds) {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

/** Relative time in plain words: "just now", "4 min ago", "Yesterday 6:10 pm". */
export function relativeTime(value, now = Date.now()) {
  if (!value) return '';
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Math.round((now - t) / 1000);
  if (diff < 0) {
    const ahead = -diff;
    if (ahead < 3600) return `in ${Math.max(1, Math.round(ahead / 60))} min`;
    return new Date(t).toLocaleString('en-IN', { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  }
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 6 * 3600) return `${Math.floor(diff / 3600)} hr ago`;
  const d = new Date(t);
  const time = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
  if (d.toDateString() === new Date(now).toDateString()) return `Today ${time}`;
  if (d.toDateString() === new Date(now - 86400000).toDateString()) return `Yesterday ${time}`;
  return `${d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} ${time}`;
}

/** "Today" | "Yesterday" | "Earlier" bucket for grouping a feed. */
export function dayBucket(value, now = Date.now()) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return 'Earlier';
  if (d.toDateString() === new Date(now).toDateString()) return 'Today';
  if (d.toDateString() === new Date(now - 86400000).toDateString()) return 'Yesterday';
  return 'Earlier';
}
