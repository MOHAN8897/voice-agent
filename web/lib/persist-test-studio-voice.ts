/** Persist Test Studio voice selection to runtime (applied on next TTS call). */
import { TEST_STUDIO_SESSION_ID } from "@/lib/test-studio-stack";

export async function persistTestStudioVoice(opts: {
  ttsSpeaker: string;
  ttsModel?: string;
}): Promise<{ ok: boolean; error?: string }> {
  const patch: Record<string, string> = { ttsSpeaker: opts.ttsSpeaker };
  if (opts.ttsModel) patch.ttsModel = opts.ttsModel;

  try {
    const r = await fetch("/api/settings/runtime", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ sessionId: TEST_STUDIO_SESSION_ID, ...patch }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      const msg = j?.detail?.error?.message || `Save failed (${r.status})`;
      return { ok: false, error: msg };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Network error" };
  }
}
