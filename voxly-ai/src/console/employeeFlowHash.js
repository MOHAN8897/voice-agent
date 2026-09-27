/** Hash helpers for unified AI Employee flow (#dashboard/employees?step=…&agent=…) */

export const EMPLOYEE_FLOW_STEPS = ['script', 'voice', 'telephony', 'test'];

const LEGACY_TAB_STEP = {
  'agent-studio': 'script',
  'talk-to-ai': 'test',
};

export function legacyEmployeeStep(tabId) {
  return LEGACY_TAB_STEP[tabId] || null;
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
