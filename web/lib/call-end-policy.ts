export type CallEndPolicyState = {
  allowedReasons: string[];
  farewell: string;
};

export const CALL_END_REASONS: { id: string; label: string }[] = [
  { id: "goodbye", label: "Goodbye / explicit end request" },
  { id: "firm_refusal", label: "Stop contacting me / do not call" },
  { id: "not_interested", label: "Not interested (not an opt-out)" },
  { id: "goal_complete", label: "Goal complete, nothing else" },
  { id: "abuse", label: "Abuse" },
  { id: "out_of_scope", label: "Still off-scope after one redirect" },
];

export const DEFAULT_CALL_END_FAREWELL: Record<string, string> = {
  "te-IN": "సరేనండి, మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.",
  "en-IN": "Thank you for your time. Goodbye.",
  "en-US": "Thank you for your time. Goodbye.",
  "en-GB": "Thank you for your time. Goodbye.",
  "hi-IN": "समय देने के लिए धन्यवाद। नमस्कार।",
  "ta-IN": "உங்கள் நேரத்திற்கு நன்றி. வணக்கம்.",
  "kn-IN": "ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಮಸ್ಕಾರ.",
  "ml-IN": "നിങ്ങളുടെ സമയത്തിന് നന്ദി. നമസ്കാരം.",
  "mr-IN": "तुमच्या वेळेबद्दल धन्यवाद. नमस्कार.",
  "bn-IN": "আপনার সময়ের জন্য ধন্যবাদ। নমস্কার।",
  "gu-IN": "તમારા સમય માટે આભાર. આવજો.",
  "pa-IN": "ਤੁਹਾਡੇ ਸਮੇਂ ਲਈ ਧੰਨਵਾਦ। ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ।",
};

const DEFAULT_ALLOWED_REASONS = ["goodbye", "firm_refusal", "not_interested", "goal_complete", "abuse"];

export function defaultCallEndPolicy(language: string): CallEndPolicyState {
  return {
    allowedReasons: [...DEFAULT_ALLOWED_REASONS],
    farewell: DEFAULT_CALL_END_FAREWELL[language] || DEFAULT_CALL_END_FAREWELL["en-IN"],
  };
}

export function normalizeCallEndPolicyState(raw: unknown, language: string): CallEndPolicyState {
  const fallback = defaultCallEndPolicy(language);
  if (!raw || typeof raw !== "object") return fallback;
  const value = raw as Record<string, unknown>;
  const reasons = Array.isArray(value.allowedReasons)
    ? (value.allowedReasons as unknown[]).map((reason) => String(reason)).filter(Boolean)
    : fallback.allowedReasons;
  const farewell = String(value.farewell || "").trim();
  const isStock = !farewell || Object.values(DEFAULT_CALL_END_FAREWELL).includes(farewell);
  return {
    allowedReasons: reasons.length ? reasons : fallback.allowedReasons,
    farewell: isStock ? fallback.farewell : farewell,
  };
}
