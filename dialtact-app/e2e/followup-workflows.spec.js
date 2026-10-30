import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

const policy = {
  enabled: false, callbackMode: 'review', missedMode: 'off', missedDelayMinutes: 30, timezone: 'UTC',
  startTime: '09:00', endTime: '18:00', weekdays: [0, 1, 2, 3, 4, 5], maxAttempts: 1,
  retryDelayMinutes: 180, dailyLimit: 20, cooldownMinutes: 360, expiryDays: 7, scoringEnabled: true,
  scoreWeights: { interest: 40, requirements: 25, timing: 25, contact: 10 },
  scoreFactKeys: { requirements: ['product', 'budget'], timing: ['callback_when'], contact: ['phone', 'email'] },
  hotThreshold: 70, warmThreshold: 40,
};

async function setup(page, { readonly = false } = {}) {
  const base = await setupVoiceWorkspace(page);
  const state = { config: { ...policy }, revision: 0, writes: [], jobWrites: [], failSave: false, failJobs: false };
  const job = { id: 'scheduled-job', agentId: base.agent.id, kind: 'callback', phone: '+12025550123',
    status: 'needs_review', reason: 'time_requires_review', requestedWhen: 'Please call later',
    timezone: 'UTC', dueAt: null, expiresAt: '2027-02-01T10:00:00Z', attempts: 0,
    createdAt: '2026-10-28T10:00:00Z', updatedAt: '2026-10-28T10:00:00Z' };
  await page.route('**/api/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (readonly && path === '/api/auth/me') return route.fulfill({ json: { user: { ...base.user, role: 'customer_viewer' }, role: 'customer_viewer', tenant: { tenantId: base.user.tenantId } } });
    if (path.endsWith('/follow-up-policy')) {
      if (req.method() === 'PUT') {
        const body = req.postDataJSON(); state.writes.push(body);
        if (state.failSave) return route.fulfill({ status: 409, json: { detail: 'Settings changed. Reload before saving.' } });
        state.config = body.config; state.revision += 1;
      }
      return route.fulfill({ json: { config: state.config, revision: state.revision, authorizedAt: state.config.enabled ? '2026-10-28T10:00:00Z' : null } });
    }
    if (path === '/api/follow-ups') return route.fulfill(state.failJobs ? { status: 503, json: { detail: 'Follow-up service unavailable' } } : { json: { jobs: job.status === 'cancelled' ? [] : [job], total: job.status === 'cancelled' ? 0 : 1 } });
    if (path === '/api/follow-ups/scheduled-job') { const body = req.postDataJSON(); state.jobWrites.push(body); job.status = body.action === 'cancel' ? 'cancelled' : 'scheduled'; job.dueAt = body.dueAt; return route.fulfill({ json: job }); }
    if (path === '/api/dnc') return route.fulfill({ json: { entries: [{ phone_e164: '+12025550123', reason: 'verbal_opt_out_live_call', added_at: '2026-10-28T10:00:00Z' }], total: 1 } });
    if (path === '/api/leads') return route.fulfill({ json: { leads: [{ leadId: 'scored', agentId: base.agent.id, name: 'Priority customer', phone: '+12025550123', stage: 'qualified', doNotCall: true,
      assessment: { score: 65, band: 'warm', disposition: 'qualified', components: [{ signal: 'interest', points: 40, max: 40, evidence: 'qualified' }] } }], total: 1, stageCounts: { qualified: 1 } } });
    if (path === '/api/calls/stats') return route.fulfill({ json: { total: 100, connected: 75, missed: 25, completedConnected: 70, avgDurationSec: 45, leadCount: 10, convertedLeads: 3, conversionRate: 30, connectRate: 75, leadStageCounts: { converted: 3, qualified: 7 }, cost: { currency: 'INR', settledSpend: 200, complete: true, costPerLead: 20 } } });
    return route.fallback();
  });
  await page.getByTestId('agent-tab-settings').click();
  await page.getByRole('button', { name: 'Follow-ups & scoring', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Allow scheduled follow-up calls' })).not.toBeChecked();
  return state;
}

test('follow-up permission needs confirmation, persists through the save dock and survives reload', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('checkbox', { name: 'Allow scheduled follow-up calls' }).check();
  await page.getByLabel('Caller-requested callbacks').selectOption('automatic');
  await page.getByLabel('Missed inbound calls').selectOption('automatic');
  await page.getByLabel('Missed-call delay (minutes)').fill('45');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-settings-error')).toContainText('Confirm follow-up call permission');
  expect(state.writes).toHaveLength(0);
  await page.getByLabel('Authorize follow-up calls and charges').check();
  await page.getByTestId('agent-save').click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0]).toMatchObject({ acknowledgeCharges: true, revision: 0, config: { enabled: true, missedDelayMinutes: 45, missedMode: 'automatic' } });
  await expect(page.getByTestId('agent-studio-unsaved')).not.toBeVisible();
  await expect(page.getByLabel('Allow scheduled follow-up calls')).toBeChecked();
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay]{display:none!important}' });
  await page.getByTestId('agent-tab-settings').click();
  await page.getByRole('button', { name: 'Follow-ups & scoring', exact: true }).click();
  await expect(page.getByLabel('Allow scheduled follow-up calls')).toBeChecked();
});

test('failed settings save preserves the draft and shows a useful error', async ({ page }) => {
  const state = await setup(page); state.failSave = true;
  await page.getByLabel('Missed-call delay (minutes)').fill('75');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-settings-error')).toContainText('Settings changed');
  await expect(page.getByLabel('Missed-call delay (minutes)')).toHaveValue('75');
  await expect(page.getByTestId('agent-studio-unsaved')).toBeVisible();
});

test('queue reviews need consent; DND and outcome priority are visible and block call controls', async ({ page }) => {
  const state = await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await expect(page.getByTestId('lead-row-scored').getByText('65/100 · warm priority')).toBeVisible();
  await expect(page.getByTestId('lead-row-scored').getByLabel('Select Priority customer')).toBeDisabled();
  await page.getByTestId('lead-row-scored').getByRole('button', { name: 'Priority customer', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Call lead', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
  await page.getByRole('button', { name: 'Callbacks & missed calls', exact: true }).click();
  await page.getByRole('button', { name: 'Review time', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Schedule follow-up', exact: true })).toBeDisabled();
  await page.getByLabel('Follow-up date and time').fill('2027-01-01T10:30');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Schedule follow-up', exact: true }).click();
  await expect.poll(() => state.jobWrites.length).toBe(1);
  expect(state.jobWrites[0]).toMatchObject({ action: 'schedule', confirm: true, expectedUpdatedAt: '2026-10-28T10:00:00Z' });
  await page.getByRole('button', { name: 'Do not call', exact: true }).click();
  await expect(page.getByTestId('add-dnc-button')).toBeVisible();
  await expect(page.getByText('verbal_opt_out_live_call')).toBeVisible();
});

test('overview shows connection, confirmed conversion and actual charge metrics', async ({ page }) => {
  await setup(page);
  await page.getByTestId('agent-tab-overview').click();
  await expect(page.getByTestId('agent-conversion-metrics')).toContainText('30%');
  await expect(page.getByTestId('agent-conversion-metrics')).toContainText('₹20.00');
  await expect(page.getByText('75%', { exact: true })).toBeVisible();
  await expect(page.getByText('45s', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Pipeline', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Lead management' })).toBeVisible();
  await expect(page.getByTestId('agent-calls-panel-tab-leads')).toHaveAttribute('aria-selected', 'true');
});

test('mobile follow-up controls fit the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.getByText('Limits, expiry & lead scoring', { exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: '../artifacts/followups-mobile.png', fullPage: true });
});

test('viewers can inspect follow-up permission and DND without mutation controls', async ({ page }) => {
  await setup(page, { readonly: true });
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay]{display:none!important}' });
  await page.getByTestId('agent-tab-settings').click();
  await page.getByRole('button', { name: 'Follow-ups & scoring', exact: true }).click();
  await expect(page.getByLabel('Allow scheduled follow-up calls')).toBeDisabled();
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByRole('button', { name: 'Do not call', exact: true }).click();
  await expect(page.getByTestId('add-dnc-button')).toBeDisabled();
});
