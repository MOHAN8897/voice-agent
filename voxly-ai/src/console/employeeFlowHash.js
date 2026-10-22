/** Hash helpers for unified AI Employee flow (#dashboard/employees?step=…&agent=…) */

export const EMPLOYEE_FLOW_STEPS = ['overview', 'script', 'calls', 'voice', 'settings'];

const LEGACY_TAB_STEP = {
  'agent-studio': 'script',
  'talk-to-ai': 'overview',
};

/**
 * Old step ids → the five-tab workspace.
 *
 * `telephony` became `calls` with the Call settings panel focused, and `test` became
 * Overview with the Test call modal already open, so old links land on the equivalent
 * screen instead of a blank tab.
 */
const LEGACY_STEP = {
  script: { step: 'script' },
  voice: { step: 'voice' },
  telephony: { step: 'settings' },
  test: { step: 'overview', openTestCall: true },
  knowledge: { step: 'script' },
};

export function legacyEmployeeStep(tabId) {
  return LEGACY_TAB_STEP[tabId] || null;
}

/** Always yields a valid step plus any one-shot intent carried over from an old link. */
export function resolveEmployeeStep(step) {
  if (!step) return { step: 'overview' };
  if (EMPLOYEE_FLOW_STEPS.includes(step)) return { step };
  return LEGACY_STEP[step] || { step: 'overview' };
}

export function parseDashboardHash(hash = typeof window !== 'undefined' ? window.location.hash : '') {
  const raw = (hash || '').replace(/^#dashboard\/?/, '');
  const [tabPart, query = ''] = raw.split('?');
  const tab = (tabPart || 'overview').split('/')[0] || 'overview';
  const params = new URLSearchParams(query);
  return {
    tab,
    step: params.get('step') || null,
    agentId: params.get('agent') || null,
  };
}

export function buildEmployeesHash({ step, agentId } = {}) {
  const params = new URLSearchParams();
  if (step && EMPLOYEE_FLOW_STEPS.includes(step)) params.set('step', step);
  if (agentId) params.set('agent', agentId);
  const q = params.toString();
  return q ? `#dashboard/employees?${q}` : '#dashboard/employees';
}

export function resolveConsoleTab(tab) {
  if (tab === 'agent-studio' || tab === 'talk-to-ai') return 'employees';
  return tab;
}