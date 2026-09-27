/** Primary languages for the “Build my employee” composer (matches product locales). */

export const EMPLOYEE_MODES = [
  { id: 'instant_lead', label: 'Instant Lead Caller', icon: 'zap' },
  { id: 'bulk', label: 'Bulk Caller', icon: 'megaphone' },
];

export const PRIMARY_LANGUAGES = [
  { code: 'en-IN', label: 'English', sub: 'India' },
  { code: 'en-US', label: 'English', sub: 'US' },
  { code: 'hi-IN', label: 'हिन्दी', sub: 'Hindi' },
  { code: 'te-IN', label: 'తెలుగు', sub: 'Telugu' },
  { code: 'ta-IN', label: 'தமிழ்', sub: 'Tamil' },
  { code: 'kn-IN', label: 'ಕನ್ನಡ', sub: 'Kannada' },
  { code: 'ml-IN', label: 'മലയാളം', sub: 'Malayalam' },
  { code: 'mr-IN', label: 'मराठी', sub: 'Marathi' },
];

export const INDUSTRY_CHIPS = [
  {
    id: 'real_estate',
    label: 'Real estate',
    emoji: '🏠',
    snippet:
      'We are a real estate developer. Greet leads, ask budget and BHK preference, offer a site visit, and confirm details on WhatsApp.',
  },
  {
    id: 'coaching',
    label: 'Coaching & tuition',
    emoji: '📚',
    snippet:
      'We run a coaching institute. Answer course and batch questions, capture grade and exam goal, and book a demo class.',
  },
  {
    id: 'clinic',
    label: 'Hospital & clinic',
    emoji: '🏥',
    snippet:
      'We are a clinic. Help with appointments, services offered, and timings; collect patient name and callback number.',
  },
  {
    id: 'dealership',
    label: 'Car & bike dealership',
    emoji: '🚗',
    snippet:
      'We sell vehicles. Qualify interest, model preference, budget range, and schedule a showroom visit or test drive.',
  },
];
