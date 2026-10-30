import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

async function setup(page, { profileFailure = false } = {}) {
  const base = await setupVoiceWorkspace(page);
  const state = { campaigns: [], mutations: [], removals: [], dnd: true, unavailable: false, imports: [], cards: [], cancellations: [] };
  const jobs = ['callback', 'missed'].map((kind, index) => ({ jobId: `aaaaaaaa-0000-4000-8000-${String(index + 7001).padStart(12, '0')}`,
    kind, phone: `+1202555012${index}`, full_name: `${kind} caller`, email: '', notes: '', timezone: 'UTC',
    dueAt: new Date(Date.now() + 6 * 3600000).toISOString(), expiresAt: new Date(Date.now() + 86400000).toISOString() }));
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    if (req.method() !== 'GET') state.mutations.push(path);
    if (path.endsWith('/follow-ups/import-review')) { state.imports.push(req.postDataJSON()); return route.fulfill({ json: { imported: 2, days: 7, reviewOnly: true } }); }
    if (profileFailure && path.endsWith('/telephony-profile')) return route.fulfill({ status: 503, json: { detail: 'Operating settings unavailable' } });
    if (path.endsWith('/follow-up-policy')) return route.fulfill({ json: { config: { enabled: false, callbackMode: 'review', missedMode: 'off', timezone: 'UTC', weekdays: [0,1,2,3,4,5,6], startTime: '09:00', endTime: '18:00', maxAttempts: 1, dailyLimit: 20, expiryDays: 7, cooldownMinutes: 360, missedDelayMinutes: 30, retryDelayMinutes: 180, scoreWeights: { interest: 40, requirements: 25, timing: 25, contact: 10 }, scoreFactKeys: {}, hotThreshold: 70, warmThreshold: 40 }, revision: 0 } });
    if (path === '/api/follow-ups') return route.fulfill({ json: { jobs: [], total: 0 } });
    if (path === '/api/callback-requests') return route.fulfill({ json: { requests: [] } });
    if (path === '/api/campaigns/audience/follow-ups') return route.fulfill({ json: state.unavailable ? { jobs: [], total: 0, unavailableReason: 'Enable this follow-up flow in agent settings first.' } : { jobs: jobs.filter(job => job.kind === url.searchParams.get('kind')), total: 1 } });
    if (path === '/api/contacts/normalize-preview') {
      const body = req.postDataJSON();
      const validContacts = body.rows.map(row => ({ ...row, custom_fields: { followup_job_id: row['custom_field:followup_job_id'], followup_kind: row['custom_field:followup_kind'] } }));
      return route.fulfill({ json: { validCount: validContacts.length, totalRows: validContacts.length, invalidCount: 0, duplicateCount: 0, validContacts, invalidContacts: [] } });
    }
    if (path === '/api/campaigns/validate-variables') return route.fulfill({ json: { scriptVersion: 'published', requiredVariables: [], missing_breakdown: {}, previews: [] } });
    if (path === '/api/campaigns' && req.method() === 'POST') {
      const body = req.postDataJSON(); state.campaigns.push(body);
      return route.fulfill({ json: { ok: true, campaign: { id: 'created-campaign', name: body.name, status: 'draft', agentId: base.agent.id, totalContacts: 1 } } });
    }
    if (path === '/api/campaigns' && req.method() === 'GET') return route.fulfill({ json: { campaigns: state.cards } });
    if (path.endsWith('/cancel')) { state.cancellations.push(path); state.cards = state.cards.map(row => ({ ...row, status: 'cancelled' })); return route.fulfill({ json: { ok: true, status: 'cancelled' } }); }
    if (path === '/api/dnc') return route.fulfill({ json: { entries: state.dnd ? [{ id: 'dnd-entry', phone_e164: jobs[0].phone, active: true, added_at: '2026-10-29T08:00:00Z' }] : [], total: state.dnd ? 1 : 0 } });
    if (path.endsWith('/deactivate')) { state.removals.push(req.postDataJSON()); state.dnd = false; return route.fulfill({ json: { ok: true } }); }
    return route.fallback();
  });
  return { ...base, state, jobs };
}

async function followupCampaign(page) {
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByRole('button', { name: 'Callbacks & missed calls', exact: true }).click();
  await page.getByRole('button', { name: 'Create follow-up campaign', exact: true }).click();
  return page.getByRole('dialog');
}

for (const kind of ['callback', 'missed']) {
  test(`campaign from ${kind} jobs preserves server references and requires approval`, async ({ page }) => {
    const { state, jobs } = await setup(page);
    const dialog = await followupCampaign(page);
    if (kind === 'missed') await dialog.getByRole('button', { name: 'Missed calls', exact: true }).click();
    const job = jobs.find(row => row.kind === kind);
    await dialog.getByLabel(`Select follow-up ${job.phone}`, { exact: true }).check();
    await dialog.getByLabel('Campaign name', { exact: true }).fill(`${kind} campaign`);
    await dialog.getByRole('button', { name: 'Validate contacts', exact: true }).click();
    await expect(dialog.getByRole('button', { name: 'Save as draft', exact: true })).toBeDisabled();
    await dialog.getByLabel(/I confirm I have authorization/).check();
    await dialog.getByRole('button', { name: 'Save as draft', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    expect(state.campaigns).toHaveLength(1);
    expect(state.campaigns[0]).toMatchObject({ followupJobIds: [job.jobId], contacts: [], consentConfirmed: true, autoStart: false });
  });
}

test('unavailable follow-ups explain the setting requirement and cannot launch', async ({ page }) => {
  const { state } = await setup(page); state.unavailable = true;
  const dialog = await followupCampaign(page);
  await expect(dialog.getByRole('alert')).toContainText('Enable this follow-up flow');
  await expect(dialog.getByTestId('campaign-launch')).toBeDisabled();
  expect(state.campaigns).toHaveLength(0);
});

test('failed operating-settings load cannot overwrite configuration or voice', async ({ page }) => {
  const { state } = await setup(page, { profileFailure: true });
  await page.getByTestId('agent-tab-settings').click();
  await page.getByTestId('agent-settings-name').fill('Keep this draft');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-settings-error')).toContainText('Operating settings unavailable');
  await expect(page.getByTestId('agent-settings-name')).toHaveValue('Keep this draft');
  expect(state.mutations.filter(path => path.includes('/agents/'))).toEqual([]);
});

test('DND removal requires a meaningful reason and explicit renewed permission', async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByRole('button', { name: 'Do not call', exact: true }).click();
  await page.getByRole('button', { name: 'Remove from DND', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByTestId('dnc-deactivate-reason-input').fill('     ');
  await dialog.getByTestId('dnc-reconsent-checkbox').check();
  await expect(dialog.getByTestId('dnc-deactivate-confirm-btn')).toBeDisabled();
  await dialog.getByTestId('dnc-deactivate-reason-input').fill('Caller renewed permission today');
  await dialog.getByTestId('dnc-deactivate-confirm-btn').click();
  await expect(dialog).not.toBeVisible();
  expect(state.removals[0]).toMatchObject({ reconsentConfirmed: true, removalReason: 'Caller renewed permission today' });
});

test('mobile follow-up campaign audience remains usable without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  const dialog = await followupCampaign(page);
  await expect(dialog.getByTestId('campaign-followup-audience')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});

test('earlier missed calls enter review without enabling automatic calling', async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByRole('button', { name: 'Callbacks & missed calls', exact: true }).click();
  await page.getByRole('button', { name: 'Import earlier calls for review', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('does not authorize automatic calls');
  await dialog.getByRole('button', { name: 'Import for review', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(state.imports).toEqual([{ kind: 'missed', days: 7 }]);
  expect(state.campaigns).toHaveLength(0);
  expect(state.mutations.some(path => path.endsWith('/follow-up-policy'))).toBe(false);
});

test('campaign cancellation stops future work only after tenant confirmation', async ({ page }) => {
  const { state, agent } = await setup(page);
  state.cards = [{ id: 'reviewed-campaign', name: 'Callback campaign', agentId: agent.id, status: 'draft', totalContacts: 1, concurrency: 1 }];
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay]{display:none!important}' });
  await page.getByRole('button', { name: 'Campaigns', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel campaign', exact: true }).click();
  expect(state.cancellations).toHaveLength(0);
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm campaign cancellation', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByText('cancelled', { exact: true })).toBeVisible();
  expect(state.cancellations).toHaveLength(1);
});

test('follow-up-only saves do not write legacy voice or operating defaults', async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId('agent-tab-settings').click();
  await page.getByRole('button', { name: 'Follow-ups & scoring', exact: true }).click();
  await page.getByLabel('Missed-call delay (minutes)').fill('45');
  await page.getByTestId('agent-save').click();
  await expect(page.getByText('All agent configurations saved successfully', { exact: true })).toBeVisible();
  expect(state.mutations.filter(path => path.includes('/agents/') && !path.endsWith('/follow-up-policy'))).toEqual([]);
});
