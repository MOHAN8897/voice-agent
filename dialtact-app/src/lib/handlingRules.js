export const HANDLING_RULES_TITLE = 'Objection & Objective Handling';
export const HANDLING_RULES_METADATA = 'saas_handling_rules';
const ACTIONS = new Set(['continue_script', 'offer_callback', 'end_call', 'transfer_human']);

export function normalizeHandlingRules(value) {
  if (!Array.isArray(value) || value.length > 50) throw new Error('Use at most 50 handling rules.');
  return value.map((rule, index) => {
    if (!rule || typeof rule !== 'object' || Array.isArray(rule)) throw new Error(`Review handling rule ${index + 1}.`);
    const kind = rule.kind || 'objection';
    const action = rule.action || 'continue_script';
    const trigger = String(rule.trigger || '').trim();
    const response = String(rule.response || '').trim();
    if (!['objection', 'objective'].includes(kind) || !ACTIONS.has(action)) throw new Error(`Review the type and action in handling rule ${index + 1}.`);
    if (rule.enabled !== false && (!trigger || !response)) throw new Error(`Complete the situation and guidance in handling rule ${index + 1}, or disable it.`);
    if (trigger.length > 2000 || response.length > 6000) throw new Error(`Shorten handling rule ${index + 1}.`);
    return { kind, category: String(rule.category || 'custom'), trigger, response, action, enabled: rule.enabled !== false };
  });
}

export function handlingRuleSections(value = []) {
  const rules = normalizeHandlingRules(value);
  const active = rules.filter(rule => rule.enabled);
  return [
    { type: 'custom', title: HANDLING_RULES_METADATA, order: 39, enabled: false, raw_text: JSON.stringify({ version: 1, rules }) },
    { type: 'faq', title: HANDLING_RULES_TITLE, order: 40, enabled: active.length > 0,
      raw_text: active.length ? '[Configured handling rules]\nApply relevant rules by meaning and conversation context in the selected call language. Answer the caller’s current question first. Objectives guide the conversation; they never override a refusal, consent, safety, supplied facts or available capabilities. Ask one necessary question at a time. Actions require a permitted tool and confirmed result. Offer callback means collect the requested timing; only the platform can confirm a saved request. A future-interest or callback request is not a complete rejection. Action end_call means propose a close for server approval; the server owns farewell and hangup. Transfer requires an available transfer tool.\n\n' + active.map(rule =>
        `[${rule.kind === 'objective' ? 'Objective' : 'Objection'}]\n[Intent: ${rule.category}]\nWhen: ${rule.trigger}\nGuidance: ${rule.response}\nAction: ${rule.action}`).join('\n\n') : '' },
  ];
}

export function storedHandlingRules(sections) {
  const metadata = sections?.find(section => section.title === HANDLING_RULES_METADATA);
  if (!metadata) return null;
  let value;
  try { value = JSON.parse(metadata.raw_text); } catch { throw new Error('Handling rules could not be read. Reload before editing.'); }
  if (!value || typeof value !== 'object' || value.version !== 1) throw new Error('This handling rule version is unsupported.');
  return normalizeHandlingRules(value.rules);
}
