import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.

const AGENT = 'voice-setup-agent';

const calls = [
  {
    call_id: 'attempt-busy', attempt_id: 'attempt-busy', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'outbound', status: 'declined', started_at: '2026-10-30T09:00:00Z', ended_at: '2026-10-30T09:00:20Z',
    end_reason: 'busy', caller_phone: '+919000000002', called_phone: '+918000000001',
    outcome_label: 'Busy', outcome_reason: 'Their line was busy.',
  },
  {
    call_id: 'attempt-noanswer', attempt_id: 'attempt-noanswer', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'outbound', status: 'missed', started_at: '2026-10-30T08:00:00Z', ended_at: '2026-10-30T08:00:40Z',
    end_reason: 'no_answer', caller_phone: '+919000000003', outcome_label: 'No answer',
    outcome_reason: "They didn't pick up before the ringing stopped.",
  },
  {
    call_id: 'attempt-inbound', attempt_id: 'attempt-inbound', is_attempt: true, connected: false, agent_id: AGENT,
    direction: 'inbound', status: 'missed', started_at: '2026-10-30T07:00:00Z', ended_at: '2026-10-30T07:00:10Z',
    end_reason: 'caller_cancelled_no_answer', caller_phone: '+919000000004', outcome_label: 'Missed call',
    outcome_reason: 'The caller hung up before the agent answered.',
  },
];

const basePolicy = {
  enabled: true, callbackMode: 'review', missedMode: 'review', missedDelayMinutes: 30, timezone: 'Asia/Kolkata',
  startTime: '09:00', endTime: '18:00', weekdays: [0, 1, 2, 3, 4, 5], maxAttempts: 1,
  retryDelayMinutes: 180, dailyLimit: 20, cooldownMinutes: 360, expiryDays: 7, scoringEnabled: true,
  scoreWeights: { interest: 40, requirements: 25, timing: 25, contact: 10 },
  scoreFactKeys: { requirements: ['product'], timing: ['callback_when'], contact: ['phone'] },
  hotThreshold: 70, warmThreshold: 40,
  // Saved before the recall settings existed: the console must fill in defaults.
};

async function setup(page) {
  const base = await setupVoiceWorkspace(page);
  const state = { callQueries: [], policyWrites: [], config: { ...basePolicy }, revision: 1 };
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    if (path === '/api/calls') {
      state.callQueries.push(url.searchParams.get('status') || '');
      const wanted = (url.searchParams.get('status') || '').split(',').filter(Boolean);
      const rows = wanted.length ? calls.filter((c) => wanted.includes(c.status)) : calls;
      return route.fulfill({ json: { calls: rows, total: rows.length, limit: 100, offset: 0 } });
    }
    if (path === '/api/calls/tags') return route.fulfill({ json: { tags: [] } });
    if (path === '/api/calls/stats') return route.fulfill({ json: { total: 3, connected: 0, missed: 2 } });
    if (path.endsWith('/follow-up-policy')) {
      if (req.method() === 'PUT') {
        const body = req.postDataJSON();
        state.policyWrites.push(body);
        state.config = body.config;
        state.revision += 1;
      }
      return route.fulfill({ json: { config: state.config, revision: state.revision, authorizedAt: '2026-10-28T10:00:00Z' } });
    }
    if (path === '/api/follow-ups') {
      return route.fulfill({ json: { total: 2, jobs: [
        { id: 'job-cb', agentId: AGENT, kind: 'callback', phone: '+919000000005', status: 'scheduled',
          reason: 'requested_window_resolved', requestedWhen: 'రేపు ఈవెనింగ్', timezone: 'Asia/Kolkata',
          dueAt: '2026-10-31T11:40:00Z', expiresAt: '2026-11-06T10:00:00Z', attempts: 0,
          resolvedWindow: { label: 'tomorrow evening', display: 'Sat 31 Oct, 5:00–7:30 pm', summary: 'tomorrow evening → Sat 31 Oct, 5:00–7:30 pm', scheduledAt: '2026-10-31T11:40:00Z' },
          createdAt: '2026-10-30T10:00:00Z', updatedAt: '2026-10-30T10:00:00Z' },
        { id: 'job-recall', agentId: AGENT, kind: 'recall', outcome: 'busy', phone: '+919000000002', status: 'needs_review',
          reason: 'approval_required', timezone: 'Asia/Kolkata', dueAt: '2026-10-30T11:00:00Z',
          expiresAt: '2026-11-06T10:00:00Z', attempts: 0, createdAt: '2026-10-30T09:01:00Z', updatedAt: '2026-10-30T09:01:00Z' },
      ] } });
    }
    if (path === '/api/callback-requests') {
      return route.fulfill({ json: { requests: [
        { id: 'cbr-1', callId: 'call-1', agentId: AGENT, phone: '+919000000005', status: 'requested',
          requestedWhen: 'రేపు ఈవెనింగ్', requestText: 'రేపు ఈవెనింగ్ కాల్ చేయండి',
          resolvedWindow: { display: 'Sat 31 Oct, 5:00–7:30 pm', summary: 'tomorrow evening → Sat 31 Oct, 5:00–7:30 pm' },
          createdAt: '2026-10-30T10:00:00Z' },
      ] } });
    }
    return route.fallback();
  });
  return { base, state };
}

test('missed, busy and unanswered calls appear in call history with plain reasons', async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-history').click();

  const busy = page.getByTestId('call-row-declined');
  await expect(busy).toContainText("couldn't reach");
  await expect(busy).toContainText('busy');
  await expect(busy.getByTestId('call-outcome-pill')).toHaveText('Busy');
  await expect(busy).toContainText('Their line was busy.');

  const missed = page.getByTestId('call-row-missed');
  await expect(missed).toHaveCount(2);
  await expect(missed.filter({ hasText: 'No answer' })).toContainText("They didn't pick up");
  await expect(missed.filter({ hasText: 'Missed call' }).first()).toContainText('The caller hung up before the agent answered.');

  // The filter offers every unanswered outcome by name and queries the server for it.
  const filter = page.getByTestId('calls-status-filter');
  await expect(filter.locator('option[value="missed"]')).toHaveText('Missed / no answer');
  await expect(filter.locator('option[value="declined"]')).toHaveText('Busy / declined');
  await expect(filter.locator('option[value="failed"]')).toHaveText('Failed');
  await expect(filter.locator('option[value="voicemail"]')).toHaveCount(1);
  await filter.selectOption('declined');
  await expect.poll(() => state.callQueries.at(-1)).toBe('declined');
  await expect(page.getByTestId('call-row-missed')).toHaveCount(0);

  await page.getByTestId('call-row-declined').click();
  await expect(page.getByTestId('call-outcome-reason')).toContainText('Their line was busy.');
  await expect(page.getByTestId('call-outcome-reason')).toContainText('This call never connected.');
});

test('auto-recall options save with consent and keep defaults for older policies', async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId('agent-tab-settings').click();
  await page.getByRole('button', { name: 'Follow-ups & scoring', exact: true }).click();
  const recall = page.getByTestId('recall-settings');
  await expect(recall).toBeVisible();
  // Defaults filled in for a policy saved before these settings existed.
  await expect(page.getByLabel('Outgoing calls not answered')).toHaveValue('off');
  await expect(page.getByLabel('Recall attempts per call')).toHaveValue('3');
  await expect(page.getByLabel('Time between attempts')).toHaveValue('120');
  await expect(page.getByTestId('recall-outcome-no_answer')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('recall-outcome-failed')).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByTestId('recall-stop-conditions')).toContainText('9:00 am and 9:00 pm');

  await page.getByLabel('Outgoing calls not answered').selectOption('automatic');
  await page.getByLabel('Recall attempts per call').selectOption('4');
  await page.getByLabel('Time between attempts').selectOption('1440');
  await page.getByLabel('Wait after a declined call').selectOption('120');
  await page.getByTestId('recall-outcome-failed').click();
  await page.getByLabel('Quiet hours', { exact: true }).check();
  await page.getByLabel('Holiday dates').fill('2026-11-14, 2026-12-25');
  await page.getByText('When callers say “evening”, “tomorrow morning”…').click();
  await page.getByLabel('Evening starts').fill('17:30');

  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-settings-error')).toContainText('Confirm follow-up call permission');
  expect(state.policyWrites).toHaveLength(0);
  await page.getByLabel('Authorize follow-up calls and charges').check();
  await page.getByTestId('agent-save').click();
  await expect.poll(() => state.policyWrites.length).toBe(1);
  expect(state.policyWrites[0]).toMatchObject({
    acknowledgeCharges: true,
    config: {
      recallOutboundMode: 'automatic', recallMaxAttempts: 4, recallSpacingMinutes: 1440,
      recallMinGapAfterRejectMinutes: 120, quietHoursEnabled: true, holidays: ['2026-11-14', '2026-12-25'],
      recallOutcomes: ['no_answer', 'busy', 'declined', 'failed'],
      dayParts: { evening: { start: '17:30', end: '19:30' } },
    },
  });
});

test('vague callback times show the resolved window in follow-ups and callback requests', async ({ page }) => {
  await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByRole('button', { name: 'Callbacks & missed calls', exact: true }).click();
  await expect(page.getByTestId('followup-requested-when')).toContainText('రేపు ఈవెనింగ్ → Sat 31 Oct, 5:00–7:30 pm');
  await expect(page.getByText('was busy: calling back')).toBeVisible();
  await expect(page.getByTestId('callback-request-list')).toContainText('Asked for: రేపు ఈవెనింగ్ → Sat 31 Oct, 5:00–7:30 pm');
});

test('mobile call history with unanswered calls fits the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-history').click();
  await expect(page.getByTestId('call-row-declined')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});
