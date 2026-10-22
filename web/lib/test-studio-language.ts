/** Single canonical call/compile language for a test-studio agent. */
export function primaryAgentLanguage(languages?: string[] | null): string {
  const first = (languages || []).map((l) => String(l || "").trim()).find(Boolean);
  return first || "te-IN";
}

export async function patchAgentLanguage(
  agentId: string,
  language: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const r = await fetch(`/api/agents/${agentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ languages: [language] }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      return { ok: false, error: j?.detail?.error?.message || `Save failed (${r.status})` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Network error" };
  }
}

export async function seedTestStudioSessionLanguage(
  sessionId: string,
  language: string
): Promise<void> {
  await Promise.all([
    fetch("/api/test-studio/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId, language }),
    }),
    fetch("/api/settings/runtime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId, sttLanguage: language }),
    }),
  ]);
}
