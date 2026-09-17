import { compileLanguageLabel } from "@/components/test-studio/CompileLanguagePicker";

const ALIASES: Record<string, string> = {
  te: "te-IN",
  "te-in": "te-IN",
  telugu: "te-IN",
  en: "en-IN",
  eng: "en-IN",
  "en-in": "en-IN",
  english: "en-IN",
  "en-us": "en-US",
  "en-gb": "en-US",
  "en-au": "en-US",
  "en-ca": "en-US",
  "en-uk": "en-US",
  "english-us": "en-US",
  "english-uk": "en-US",
  american: "en-US",
  british: "en-US",
  hi: "hi-IN",
  "hi-in": "hi-IN",
  hindi: "hi-IN",
};

const SUPPORTED = new Set(["te-IN", "en-IN", "en-US", "hi-IN"]);

export function normalizeLanguageCode(code: string | null | undefined): string {
  const raw = String(code || "").trim();
  if (!raw) return "te-IN";
  if (SUPPORTED.has(raw)) return raw;
  const collapsed = raw.toLowerCase().split("_").join("-").split(" ").join("");
  if (collapsed in ALIASES) return ALIASES[collapsed];
  const compact = collapsed.split("-").join("");
  if (compact === "enus" || compact === "engb" || compact === "enuk") return "en-US";
  if (compact === "enin" || compact === "eng") return "en-IN";
  if (compact === "tein") return "te-IN";
  if (compact === "hiin") return "hi-IN";
  if (collapsed === "telugu") return "te-IN";
  if (collapsed === "english") return "en-IN";
  if (collapsed === "hindi") return "hi-IN";
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
