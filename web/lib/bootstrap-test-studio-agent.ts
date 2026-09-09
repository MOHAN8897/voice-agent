import { normalizeLanguageCode, notifyTestStudioAgentsChanged } from "@/lib/agent-language";
import { testStudioSessionId } from "@/lib/test-studio-stack";
import { patchPrefsCache } from "@/components/test-studio/useTestStudioPrefs";

/** Seed a new agent lab with the chosen call language (prefs + STT runtime). */
export async function bootstrapTestStudioAgent(agentId: string, language: string): Promise<void> {
  const lang = normalizeLanguageCode(language);
  const sessionId = testStudioSessionId(agentId);

  await Promise.all([
    fetch("/api/test-studio/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId, language: lang }),
    }),
    fetch("/api/settings/runtime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId, sttLanguage: lang }),
    }),
  ]);
  patchPrefsCache(sessionId, { language: lang });
}

export async function syncAgentCallLanguage(agentId: string, language: string): Promise<boolean> {
  const lang = normalizeLanguageCode(language);
  const r = await fetch(`/api/agents/${agentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ languages: [lang] }),
  });
  return r.ok;
}

/** Persist call language for web + PSTN: agent record, UI prefs, STT, compiled spoken pack. */
export async function persistAgentCallLanguage(opts: {
  agentId: string;
  sessionId: string;
  language: string;
}): Promise<boolean> {
  const lang = normalizeLanguageCode(opts.language);
  patchPrefsCache(opts.sessionId, { language: lang });
  const [agentOk] = await Promise.all([
    syncAgentCallLanguage(opts.agentId, lang),
    fetch("/api/test-studio/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId: opts.sessionId, language: lang }),
    }),
    fetch("/api/settings/runtime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId: opts.sessionId, sttLanguage: lang }),
    }),
    fetch("/api/instructions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        sessionId: opts.sessionId,
        language_code: lang,
        reassembleOnly: true,
      }),
    }).catch(() => null),
  ]);
  if (agentOk) notifyTestStudioAgentsChanged();
  return agentOk;
}
