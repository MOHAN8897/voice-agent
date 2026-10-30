/**
 * Mask a contact number the same way the Home feed does
 * (server/services/saas/activity_feed_service.py → mask_phone):
 *   "+919876543123" → "+91 98••• ••123".
 * Summaries and lists show the masked form; detail screens keep the full number.
 */
export function maskPhone(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const digits = raw.replace(/\D/g, '');
  if (digits.length < 7) return '•'.repeat(Math.max(3, digits.length));
  // Indian numbers arrive as +91XXXXXXXXXX, 91XXXXXXXXXX or a bare 10-digit mobile.
  if (digits.startsWith('91') && digits.length === 12 && (raw.startsWith('+') || '6789'.includes(digits[2]))) {
    const local = digits.slice(2);
    return `+91 ${local.slice(0, 2)}••• ••${local.slice(-3)}`;
  }
  if (!raw.startsWith('+') && digits.length === 10 && '6789'.includes(digits[0])) {
    return `+91 ${digits.slice(0, 2)}••• ••${digits.slice(-3)}`;
  }
  if (raw.startsWith('+') && digits.startsWith('1') && digits.length === 11) {
    return `+1 ${digits.slice(1, 4)}•••${digits.slice(-3)}`;
  }
  return `${raw.startsWith('+') ? '+' : ''}${digits.slice(0, 3)}•••${digits.slice(-3)}`;
}

/** A contact's display name, falling back to their masked number. */
export function contactName(name, phone, fallback = 'Unknown caller') {
  const clean = String(name ?? '').trim();
  // Some records store the number itself as the name; never show it unmasked.
  if (/^\+?[\d\s()-]{7,}$/.test(clean)) return maskPhone(clean) || fallback;
  if (clean && clean !== '—' && clean.toLowerCase() !== 'caller' && clean.toLowerCase() !== 'unknown caller') return clean;
  return maskPhone(phone) || fallback;
}
