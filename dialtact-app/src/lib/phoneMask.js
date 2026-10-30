/**
 * Format a contact number for display, the same way the Home feed does
 * (server/services/saas/activity_feed_service.py → format_phone):
 *   "+919398247132" → "+91 93982 47132"
 *   "+12025550123"  → "+1 202 555 0123"
 * These are the tenant's own customers, so console users see the full number.
 * Raw digit strings are never shown as-is; they are always grouped.
 */
export function formatPhone(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const digits = raw.replace(/\D/g, '');
  if (!digits) return raw;
  // Short codes / extensions: show the digits as they are.
  if (digits.length < 7) return digits;
  // Indian numbers arrive as +91XXXXXXXXXX, 91XXXXXXXXXX or a bare 10-digit mobile.
  if (digits.startsWith('91') && digits.length === 12 && (raw.startsWith('+') || '6789'.includes(digits[2]))) {
    const local = digits.slice(2);
    return `+91 ${local.slice(0, 5)} ${local.slice(5)}`;
  }
  if (!raw.startsWith('+') && digits.length === 10 && '6789'.includes(digits[0])) {
    return `+91 ${digits.slice(0, 5)} ${digits.slice(5)}`;
  }
  // Indian landline with trunk zero, e.g. 04023456789.
  if (!raw.startsWith('+') && digits.length === 11 && digits[0] === '0') {
    return `+91 ${digits.slice(1, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`;
  }
  if (raw.startsWith('+') && digits.startsWith('1') && digits.length === 11) {
    return `+1 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }
  // Anything else: groups of three, the last group taking up to four digits.
  const plus = raw.startsWith('+') ? '+' : '';
  const groups = [];
  let rest = digits;
  while (rest.length > 4) {
    groups.push(rest.slice(0, 3));
    rest = rest.slice(3);
  }
  if (rest) groups.push(rest);
  return plus + groups.join(' ');
}

/** @deprecated Numbers are no longer masked in the console; kept so old imports keep working. */
export const maskPhone = formatPhone;

/** True when a "name" is really a phone number (some records store the number as the name). */
export function looksLikePhone(value) {
  return /^\+?[\d\s()-]{7,}$/.test(String(value ?? '').trim());
}

/** A contact's display name, falling back to their formatted number. */
export function contactName(name, phone, fallback = 'Unknown caller') {
  const clean = String(name ?? '').trim();
  // A number stored as the name is shown formatted, never as a raw digit string.
  if (looksLikePhone(clean)) return formatPhone(clean) || fallback;
  if (clean && clean !== '—' && clean.toLowerCase() !== 'caller' && clean.toLowerCase() !== 'unknown caller') return clean;
  return formatPhone(phone) || fallback;
}
