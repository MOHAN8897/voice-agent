// One set of rules for every place a tenant starts an outgoing call: the agent
// workspace test call (phone), the agent's Calls tab → Outgoing → Single call,
// and the Calls page "Place a call". Validation, caller-line choice, cost and
// error copy live here so the three forms cannot drift apart again.

/** Tenant copy for a call the voice service refused (server: call_setup_failures.py). */
export const VOICE_SERVICE_UNAVAILABLE_COPY =
  "We couldn't start this call because the voice service is temporarily unavailable. " +
  "You weren't charged. Please try again in a few minutes.";

const FRIENDLY_BY_CODE = {
  voice_service_unavailable: VOICE_SERVICE_UNAVAILABLE_COPY,
  insufficient_balance: 'Your wallet balance is too low for this call. Add funds and try again.',
  dial_in_progress: 'This call is already being placed. Check call history before trying again.',
  dial_pending: 'This call is already being placed. Check call history before trying again.',
};

/**
 * Turn what a person typed into E.164, or explain what is wrong.
 * Spaces, dashes and brackets are ignored; 00 becomes +; a bare 10-digit number
 * is treated as Indian (+91), like the rest of the console.
 */
export function normalizeDestination(raw) {
  const typed = String(raw || '').trim();
  if (!typed) return { ok: false, error: 'Enter the number to call with its country code, like +91 98765 43210.' };
  let clean = typed.replace(/[\s().-]/g, '');
  if (!/^(?:\+|00)?\d+$/.test(clean)) return { ok: false, error: 'Use digits and a country code, such as +91.' };
  if (clean.startsWith('00')) clean = `+${clean.slice(2)}`;
  if (!clean.startsWith('+')) clean = clean.length === 10 ? `+91${clean}` : `+${clean}`;
  if (!/^\+[1-9]\d{7,14}$/.test(clean)) {
    return { ok: false, error: 'Enter a valid phone number with its country code, like +91 98765 43210.' };
  }
  return { ok: true, e164: clean };
}

const lineValue = (n) => n?.e164 || n?.number || '';

/**
 * Lines this workspace can call out from, the agent's own line first.
 * Released, failed and outbound-disabled lines are left out.
 */
export function outboundLines(phoneNumbers = [], agent = null) {
  const agentId = agent?.id || null;
  const usable = (phoneNumbers || []).filter(
    (n) => ['active', 'provisioned'].includes(n?.status || 'active') && n?.outboundEnabled !== false && lineValue(n)
  );
  const isAgents = (n) => Boolean(agentId && (n.assignedAgentId === agentId || (agent?.numberId && n.id === agent.numberId)));
  return [...usable]
    .sort((a, b) => Number(isAgents(b)) - Number(isAgents(a)))
    .map((n) => ({
      value: lineValue(n),
      assignedToAgent: isAgents(n),
      label: `${n.label ? `${n.label} · ` : ''}${lineValue(n)}${isAgents(n) ? ' (this agent’s number)' : n.locality ? ` · ${n.locality}` : ''}`,
    }));
}

/** The line a call uses when the tenant has not picked one. */
export function defaultOutboundLine(lines, preferred) {
  return lines.find((l) => l.assignedToAgent)?.value
    || (lines.some((l) => l.value === preferred) ? preferred : '')
    || lines[0]?.value
    || '';
}

function tierFamily(tier) {
  if (tier.startsWith('low') || tier.includes('economical') || tier.includes('budget')) return 'low';
  if (tier.startsWith('prem') || tier.includes('flagship') || tier.includes('high')) return 'premium';
  return 'medium';
}

/** Per-minute price of a phone call for this agent's voice tier, or null when unknown. */
export function phoneCallRate(wallet, agent) {
  const tier = String(agent?.defaultTier || agent?.default_tier || agent?.tier || 'medium').toLowerCase();
  const family = tierFamily(tier);
  const pick = (key) => {
    const direct = Number(wallet?.tierRates?.[tier]?.[key]);
    if (direct > 0) return direct;
    const parent = Number(wallet?.tierRates?.[family]?.[key]);
    if (parent > 0) return parent;
    return null;
  };
  const legacyInr = { low: wallet?.pstnLowRateInrPerMin, medium: wallet?.pstnMediumRateInrPerMin, premium: wallet?.pstnPremiumRateInrPerMin }[family];
  const inr = pick('inrPerMin') ?? (Number(legacyInr) > 0 ? Number(legacyInr) : Number(wallet?.rateInrPerMin) || 0);
  const usd = pick('usdPerMin') ?? (Number(wallet?.rateUsdPerMin) || 0);
  return inr > 0 && usd > 0 ? { inr, usd } : null;
}

export function walletIsEmpty(wallet) {
  return !(Number(wallet?.balanceUsd) > 0) && !(Number(wallet?.balanceInr) > 0);
}

export function isFundsError(err) {
  return err?.status === 402 || err?.code === 'insufficient_balance' || /wallet|balance|funds|credit/i.test(err?.message || '');
}

/** The sentence a tenant sees when a call could not be placed. */
export function outboundCallErrorMessage(err) {
  if (!err) return 'The call could not be placed. Please try again.';
  if (FRIENDLY_BY_CODE[err.code]) {
    // The server's own sentence wins when it is the tenant-readable one.
    return err.code === 'voice_service_unavailable' && err.message && !/^HTTP \d+/.test(err.message)
      ? err.message
      : FRIENDLY_BY_CODE[err.code];
  }
  if (err.status === 402) return FRIENDLY_BY_CODE.insufficient_balance;
  return err.message || 'The call could not be placed. Please try again.';
}
