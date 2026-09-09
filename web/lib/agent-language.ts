import { compileLanguageLabel } from "@/components/test-studio/CompileLanguagePicker";

const ALIASES: Record<string, string> = {
  te: "te-IN",
  "te-in": "te-IN",
  en: "en-IN",
  "en-in": "en-IN",
  "en-us": "en-IN",
  "en-gb": "en-IN",
  hi: "hi-IN",
  "hi-in": "hi-IN",
};

const SUPPORTED = new Set(["te-IN", "en-IN", "hi-IN"]);

export function normalizeLanguageCode(code: string | null | undefined): string {
  const raw = String(code || "").trim();
  if (!raw) return "te-IN";
  if (SUPPORTED.has(raw)) return raw;
  const lower = raw.toLowerCase();
  if (lower in ALIASES) return ALIASES[lower];
  if (lower === "telugu") return "te-IN";
  if (lower === "english") return "en-IN";
  if (lower === "hindi") return "hi-IN";
  return "te-IN";
}

/** One canonical call language per agent — first entry only. */
export function primaryAgentLanguage(agent: { languages?: unknown } | null | undefined): string {
  const langs = agent?.languages;
  if (Array.isArray(langs) && langs.length > 0) {
    return normalizeLanguageCode(String(langs[0]));
  }
  if (typeof langs === "string" && langs.trim()) {
    const trimmed = langs.trim();
    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
      const inner = trimmed.slice(1, -1).split(",")[0]?.replace(/"/g, "").trim();
      if (inner) return normalizeLanguageCode(inner);
    }
    return normalizeLanguageCode(trimmed);
  }
  return "te-IN";
}

export function formatAgentLanguage(agent: { languages?: unknown } | null | undefined): string {
  return compileLanguageLabel(primaryAgentLanguage(agent));
}

export const TEST_STUDIO_AGENTS_CHANGED = "test-studio-agents-changed";

export function notifyTestStudioAgentsChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(TEST_STUDIO_AGENTS_CHANGED));
  }
}
