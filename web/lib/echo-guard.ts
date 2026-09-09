/** Cooldown after agent speech before accepting STT finals (ms). */
export const POST_SPEAK_COOLDOWN_MS = 1200;

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function wordOverlapRatio(user: string, agent: string): number {
  const userWords = user.split(" ").filter((w) => w.length > 1);
  if (!userWords.length) {
    if (user.length >= 6 && agent.includes(user.slice(0, Math.min(user.length, 12)))) return 0.7;
    return 0;
  }
  const agentWords = new Set(agent.split(" ").filter((w) => w.length > 1));
  const overlap = userWords.filter((w) => agentWords.has(w)).length;
  return overlap / userWords.length;
}

/** True when STT final text likely matches recent agent TTS (speaker echo). */
export function isLikelyEcho(sttText: string, assistantText: string): boolean {
  const user = normalize(sttText);
  const agent = normalize(assistantText);
  if (!user || !agent || user.length < 4) return false;
  if (agent.includes(user)) return true;
  if (user.includes(agent) && agent.length > 8) return true;
  const userWords = user.split(" ").filter((w) => w.length > 1);
  if (userWords.length < 2) return false;
  return wordOverlapRatio(user, agent) >= 0.65;
}

/**
 * Stricter echo check for live partials during agent speech (speakerphone bleed).
 * Uses a lower overlap bar so mis-transcribed echo still blocks barge-in.
 */
export function isLikelyEchoPartial(sttText: string, assistantText: string): boolean {
  const user = normalize(sttText);
  const agent = normalize(assistantText);
  if (!user || !agent || user.length < 3) return false;
  if (agent.includes(user)) return true;
  if (user.length >= 6 && user.includes(agent.slice(0, Math.min(agent.length, 24)))) return true;
  const userWords = user.split(" ").filter((w) => w.length > 1);
  if (userWords.length < 2) return false;
  return wordOverlapRatio(user, agent) >= 0.45;
}
