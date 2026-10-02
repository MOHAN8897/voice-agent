/**
 * Constants for agent creation and the agent page's phone settings.
 *
 * Creation itself is one step (brief + language + role). Everything below the
 * creation form is edited on the agent page, which is why the business-hours
 * helpers live here alongside the form options.
 */

export const CALL_MODES = [
  {
    id: 'instant_lead',
    label: 'Instant lead caller',
    description: 'One new lead per call. Best for campaigns and ad traffic.',
  },
  {
    id: 'bulk',
    label: 'Bulk caller',
    description: 'Works a list of contacts. Best for follow-ups and existing customers.',
  },
];

export const AGENT_ROLES = [
  { id: 'sales', label: 'Sales' },
  { id: 'lead_qualification', label: 'Lead qualification' },
  { id: 'support', label: 'Customer support' },
  { id: 'appointment', label: 'Appointment booking' },
  { id: 'follow_up', label: 'Follow-up' },
  { id: 'information', label: 'Information' },
  { id: 'other', label: 'Something else' },
];

/**
 * Fallback labels only.
 *
 * Which languages are actually offered is a platform setting owned by the admin
 * API (`GET /api/app/agents/languages`) — an operator can enable or disable
 * languages without a frontend deploy. This list only labels the codes that come
 * back; it never decides which ones exist.
 */
export const LANGUAGE_LABELS = {
  'en-US': { label: 'English (US)', sub: 'US English' },
  'en-GB': { label: 'English (UK)', sub: 'UK English' },
  'en-IN': { label: 'English (India)', sub: 'Neutral Indian English' },
  'hi-IN': { label: 'Hindi', sub: 'हिन्दी' },
  'te-IN': { label: 'Telugu', sub: 'తెలుగు' },
  'ta-IN': { label: 'Tamil', sub: 'தமிழ்' },
  'kn-IN': { label: 'Kannada', sub: 'ಕನ್ನಡ' },
  'ml-IN': { label: 'Malayalam', sub: 'മലയാളം' },
  'mr-IN': { label: 'Marathi', sub: 'मराठी' },
  'bn-IN': { label: 'Bengali', sub: 'বাংলা' },
  'gu-IN': { label: 'Gujarati', sub: 'ગુજરાતી' },
  'pa-IN': { label: 'Punjabi', sub: 'ਪੰਜਾਬੀ' },
};

/** Last-resort default so the picker is never empty if the API is unreachable. */
export const DEFAULT_ENABLED_LANGUAGE_CODES = ['en-US', 'en-IN'];

export function describeLanguage(code) {
  return LANGUAGE_LABELS[code] || { label: code, sub: code };
}

/** Map an API language list into picker entries. */
export function toLanguageOptions(languages) {
  if (!Array.isArray(languages) || languages.length === 0) {
    return DEFAULT_ENABLED_LANGUAGE_CODES.map((code) => ({ code, ...describeLanguage(code) }));
  }
  return languages.map((lang) => {
    const code = typeof lang === 'string' ? lang : lang.code;
    return { code, ...describeLanguage(code), ...(typeof lang === 'object' && lang.label ? { label: lang.label } : {}) };
  });
}

export const INDUSTRY_CHIPS = [
  {
    id: 'real_estate',
    label: 'Real estate',
    emoji: '🏠',
    snippet:
      'We sell flats and plots. Ask which project they are interested in, their budget and preferred configuration, then book a site visit.',
  },
  {
    id: 'clinic',
    label: 'Clinic / doctor',
    emoji: '🏥',
    snippet:
      'We are a clinic. Confirm the patient name and the reason for the call, book an appointment with the right doctor, and repeat the date and time back.',
  },
  {
    id: 'dealership',
    label: 'Car dealership',
    emoji: '🚗',
    snippet:
      'We sell new and used cars. Ask which model they want, their budget and preferred colour, then arrange a test drive at the showroom.',
  },
  {
    id: 'coaching',
    label: 'Coaching / education',
    emoji: '📚',
    snippet:
      'We run coaching classes. Ask which course and which student, then share the next batch start date and confirm a counselling call.',
  },
  {
    id: 'real_estate_support',
    label: 'Property support',
    emoji: '🔑',
    snippet:
      'We handle property paperwork. Ask which property, then collect the owner details and confirm the documents needed for the next step.',
  },
  {
    id: 'restaurant',
    label: 'Restaurant',
    emoji: '🍽️',
    snippet:
      'We take table reservations. Ask for the date, time and party size, then confirm the booking name and any dietary requirements.',
  },
];

export const AFTER_HOURS_OPTIONS = [
  {
    id: 'voicemail',
    label: 'Take a voicemail',
    description: 'Callers hear a greeting and can leave a message.',
  },
  {
    id: 'hangup',
    label: 'Do not answer',
    description: 'The line rings out. No answer, no voicemail.',
  },
  {
    id: 'transfer',
    label: 'Transfer to a number',
    description: 'Send the call to a phone number you choose.',
  },
  {
    id: 'always',
    label: 'Always answer',
    description: 'The agent takes the call at any hour.',
  },
];

export const WEEKDAYS = [
  { id: 'mon', label: 'Mon' },
  { id: 'tue', label: 'Tue' },
  { id: 'wed', label: 'Wed' },
  { id: 'thu', label: 'Thu' },
  { id: 'fri', label: 'Fri' },
  { id: 'sat', label: 'Sat' },
  { id: 'sun', label: 'Sun' },
];

export const DEFAULT_BUSINESS_HOURS = {
  mon: [{ open: '09:00', close: '18:00' }],
  tue: [{ open: '09:00', close: '18:00' }],
  wed: [{ open: '09:00', close: '18:00' }],
  thu: [{ open: '09:00', close: '18:00' }],
  fri: [{ open: '09:00', close: '18:00' }],
  sat: [{ open: '09:00', close: '14:00' }],
};

export function emptyBusinessHours() {
  return {};
}

export function isBusinessHoursEmpty(hours) {
  if (!hours || typeof hours !== 'object') return true;
  const DAYS = new Set(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']);
  return Object.entries(hours).every(
    ([key, windows]) => !DAYS.has(key) || !Array.isArray(windows) || windows.length === 0
  );
}

export function countOpenDays(hours) {
  if (isBusinessHoursEmpty(hours)) return 0;
  return Object.values(hours).filter((windows) => Array.isArray(windows) && windows.length > 0).length;
}

export function businessHoursSummary(hours) {
  if (isBusinessHoursEmpty(hours)) return 'Always open';
  const open = countOpenDays(hours);
  const sample = Object.values(hours).find((w) => Array.isArray(w) && w.length > 0);
  const window = sample?.[0];
  const range = window ? `${window.open}–${window.close}` : '';
  return `${open} day${open === 1 ? '' : 's'} a week${range ? `, ${range}` : ''}`;
}

export const BRIEF_PLACEHOLDER =
  'Example: We are Sai Constructions in Hyderabad. Greet callers about our flats, ask budget and 2/3 BHK, book a site visit, thank them and confirm WhatsApp follow-up.';

export const BRIEF_MIN_CHARS = 8;
