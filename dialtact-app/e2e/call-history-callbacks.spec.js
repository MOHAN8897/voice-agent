import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.

const AGENT = 'voice-setup-agent';

// A busy call, its manual callback (declined), and that callback's callback (answered).
const calls = [
  {
    call_id: 'call-answered', is_attempt: false, connected: true, agent_id: AGENT, direction: 'outbound',
    status: 'outbound', started_at: '2026-10-31T07:40:02Z', ended_at: '2026-10-31T07:40:26Z', duration_sec: 24,
    caller_phone: '+918897908470',
    callback_of: { id: 'attempt-declined', mode: 'manual', by: 'Mohan', at: '2026-10-31T07:39:47Z' },
    callbacks: null,
  },
  {
    call_id: 'attempt-declined', attempt_id: 'attempt-declined', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'outbound', status: 'declined', started_at: '2026-10-31T07:35:59Z', end_reason: 'rejected',
    caller_phone: '+918897908470', outcome_kind: 'declined', outcome_label: 'Declined',
    outcome_reason: 'They declined the call.',
    callback_of: { id: 'attempt-busy', mode: 'manual', by: 'Mohan', at: '2026-10-31T07:35:53Z' },
    callbacks: { count: 1, last_at: '2026-10-31T07:39:47Z', last_status: 'dialed', last_result: 'Answered', last_mode: 'manual' },
  },
  {
    call_id: 'attempt-busy', attempt_id: 'attempt-busy', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'outbound', status: 'declined', started_at: '2026-10-31T07:34:52Z', end_reason: 'busy',
    caller_phone: '+918897908470', outcome_kind: 'busy', outcome_label: 'Busy', outcome_reason: 'Their line was busy.',
    callback_of: null,
    callbacks: { count: 1, last_at: '2026-10-31T07:35:53Z', last_status: 'dialed', last_result: 'Declined', last_mode: 'manual' },
  },
  {
    call_id: 'attempt-off', attempt_id: 'attempt-off', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'outbound', status: 'failed', started_at: '2026-10-31T06:00:00Z', end_reason: 'unreachable',
    caller_phone: '+919000000011', outcome_kind: 'unreachable', outcome_label: 'Unreachable',
    outcome_reason: 'Their phone was switched off or out of coverage.',
  },
];

async function setup(page, { warnings } = {}) {
  await setupVoiceWorkspace(page);
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/calls') {
      const wanted = (url.searchParams.get('status') || '').split(',').filter(Boolean);
      const rows = wanted.length ? calls.filter((c) => wanted.includes(c.status)) : calls;
      return route.fulfill({ json: { calls: rows, total: rows.length, limit: 100, offset: 0 } });
    }
    if (path === '/api/calls/tags') return route.fulfill({ json: { tags: [] } });
    if (path === '/api/calls/stats') return route.fulfill({ json: { total: calls.length, connected: 1, missed: 0 } });
    if (path.endsWith('/callbacks')) return route.fulfill({ json: { callbacks: [] } });
    if (path.endsWith('/call-warnings')) {
      return route.fulfill({ json: warnings || { recordingDisclosureOff: false, skippedActions: [], unansweredQuestions: [] } });
    }
    return route.fallback();
  });
}

async function openHistory(page) {
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-history').click();
}

test('each callback is its own history row, linked to the call it returned', async ({ page }) => {
  await setup(page);
  await openHistory(page);

  const rows = page.getByRole('list', { name: 'Calls' }).getByRole('listitem');
  await expect(rows).toHaveCount(4);

  const busy = page.getByTestId('call-row-declined').filter({ hasText: 'Busy' });
  await expect(busy.getByTestId('call-outcome-pill')).toHaveText('Busy');
  await expect(busy.getByTestId('call-called-back')).toHaveText('Called back · Declined');
  await expect(busy.getByTestId('call-callback-of')).toHaveCount(0);

  const declined = page.getByTestId('call-row-declined').filter({ hasText: 'Declined' }).first();
  await expect(declined.getByTestId('call-callback-of')).toHaveText('Callback by Mohan');
  await expect(declined.getByTestId('call-called-back')).toHaveText('Called back · Answered');

  const answered = page.getByTestId('call-row-outbound');
  await expect(answered.getByTestId('call-callback-of')).toHaveText('Callback by Mohan');

  // The detail panel links back to the call it returned.
  await declined.click();
  await expect(page.getByTestId('call-outcome-next')).toContainText('pressed decline');
  await expect(page.getByTestId('call-callbacks-summary')).toContainText('Called back once');
  await page.getByTestId('call-callback-of-link').getByRole('button', { name: 'Open the original call' }).click();
  await expect(page.getByTestId('call-outcome-next')).toContainText('on another call');
});

test('the status filter narrows to one reason', async ({ page }) => {
  await setup(page);
  await openHistory(page);
  const filter = page.getByTestId('calls-status-filter');

  const list = page.getByRole('list', { name: 'Calls' });

  await filter.selectOption('declined:busy');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await expect(list.getByTestId('call-outcome-pill')).toHaveText('Busy');

  await filter.selectOption('declined:declined');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await expect(list.getByTestId('call-outcome-pill')).toHaveText('Declined');

  await filter.selectOption('failed:unreachable');
  await expect(list.getByTestId('call-outcome-pill')).toHaveText('Unreachable');

  // The whole status still shows both reasons.
  await filter.selectOption('declined');
  await expect(page.getByRole('list', { name: 'Calls' }).getByRole('listitem')).toHaveCount(2);
});

test('needs-your-attention closes and returns only for something new', async ({ page }) => {
  const warnings = {
    recordingDisclosureOff: true,
    skippedActions: [{ action: 'GMAIL_CREATE_DRAFT', count: 2, missing: ['caller email'] }],
    unansweredQuestions: [{ question: 'Do you give bulk discounts?', count: 1 }],
  };
  await setup(page, { warnings });
  const card = page.getByTestId('agent-call-warnings');
  await page.getByTestId('agent-tab-overview').click();
  await expect(card).toBeVisible();
  await page.getByTestId('agent-call-warnings-close').click();
  await expect(card).toHaveCount(0);

  // Same warnings after a reload: still closed.
  await page.reload();
  await page.getByTestId('agent-tab-overview').click();
  await expect(page.getByTestId('agent-tab-overview')).toHaveAttribute('aria-selected', 'true');
  await expect(card).toHaveCount(0);

  // A new unanswered question brings the card back, showing only the new item.
  warnings.unansweredQuestions.push({ question: 'Do you deliver outside Hyderabad?', count: 1 });
  await page.reload();
  await page.getByTestId('agent-tab-overview').click();
  await expect(card).toBeVisible();
  await expect(card.getByTestId('warning-unanswered-questions')).toContainText('Do you deliver outside Hyderabad?');
  await expect(card.getByTestId('warning-unanswered-questions')).not.toContainText('bulk discounts');
  await expect(card.getByTestId('warning-recording-disclosure')).toHaveCount(0);
});
