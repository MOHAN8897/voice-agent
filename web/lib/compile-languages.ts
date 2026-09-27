/** Shared call/compile languages for Test Studio (UI labels; server may map to brain packs). */
export type CompileLanguageOption = {
  id: string;
  label: string;
  native?: string;
  group: "India" | "English (global)";
};

export const COMPILE_LANGUAGE_OPTIONS: CompileLanguageOption[] = [
  { id: "te-IN", label: "Telugu", native: "తెలుగు", group: "India" },
  { id: "hi-IN", label: "Hindi", native: "हिन्दी", group: "India" },
  { id: "ta-IN", label: "Tamil", native: "தமிழ்", group: "India" },
  { id: "kn-IN", label: "Kannada", native: "ಕನ್ನಡ", group: "India" },
  { id: "ml-IN", label: "Malayalam", native: "മലയാളം", group: "India" },
  { id: "mr-IN", label: "Marathi", native: "मराठी", group: "India" },
  { id: "bn-IN", label: "Bengali", native: "বাংলা", group: "India" },
  { id: "gu-IN", label: "Gujarati", native: "ગુજરાતી", group: "India" },
  { id: "pa-IN", label: "Punjabi", native: "ਪੰਜਾਬੀ", group: "India" },
  { id: "en-IN", label: "English (India)", native: "Indian English", group: "India" },
  { id: "en-US", label: "English (US)", native: "English", group: "English (global)" },
  { id: "en-GB", label: "English (UK)", native: "English", group: "English (global)" },
];

export function compileLanguageLabel(id: string): string {
  return COMPILE_LANGUAGE_OPTIONS.find((l) => l.id === id)?.label ?? id;
}
