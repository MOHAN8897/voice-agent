/** Build first-draft agent instructions from wizard fields (editable before publish). */

export function defaultGreeting(name, role) {
  const who = (name || 'our team').trim();
  const r = (role || 'assistant').toLowerCase();
  return `Hello, thanks for calling. You're speaking with ${who}, your ${r}. How can I help you today?`;
}

export function composeAgentScript({ name, role, languageLabel, businessSummary, goals, tone }) {
  const agentName = (name || 'the voice agent').trim();
  const agentRole = (role || 'customer support').trim();
  const biz = (businessSummary || 'this business').trim();
  const goalText = (goals || 'help callers clearly and politely').trim();
  const style = (tone || 'warm, concise, and professional').trim();
  const lang = languageLabel || "the agent's configured language";

  return `You are ${agentName}, an AI phone ${agentRole} for ${biz}.

Primary goals:
- ${goalText}

How to speak:
- Sound ${style}.
- Speak only ${lang} throughout the call. For a language mismatch, politely ask once to use this language; if it persists, request a callback in their language using the language callback tool.
- Keep answers short enough for voice — one or two sentences unless the caller asks for detail.

Rules:
- Stay on topic for ${biz}. If you do not know something, say so and offer a callback or to take a message.
- Never invent prices, policies, or appointments that are not in these instructions.
- Confirm names, phone numbers, and times by repeating them back.

When the call should end:
- Thank the caller and use a brief closing once their question is resolved or they say goodbye.`;
}
