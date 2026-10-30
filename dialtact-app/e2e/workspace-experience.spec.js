import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

async function leadsFixture(page) {
  const fixture = await setupVoiceWorkspace(page);
  const state = { ...fixture, patches: [], calls: [], validations: [], campaigns: [], queries: [], failSave: false, failList: false, failCall: false };
  state.leads = Array.from({ length: 27 }, (_, index) => ({
    leadId: `lead-${index}`, agentId: fixture.agent.id, name: `Customer ${String(index).padStart(2, '0')}`,
    email: `customer${index}@example.invalid`, phone: index === 2 ? '' : `+1202555${String(index + 100).padStart(4, '0')}`,
    stage: index % 2 ? 'new' : 'qualified', notes: `Enquiry ${index} needs a demo`,
    createdAt: '2026-10-20T09:00:00Z', updatedAt: '2026-10-27T09:00:00Z',
  }));
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const data = request.method() === 'GET' ? null : request.postDataJSON();
    if (path === '/api/leads' && request.method() === 'GET') {
      state.queries.push(url.search);
      if (state.failList) return route.fulfill({ status: 503, json: { detail: 'Lead service unavailable' } });
      const params = url.searchParams, q = (params.get('search') || '').toLowerCase();
      const rows = state.leads.filter(lead => (!params.get('agentId') || lead.agentId === params.get('agentId')) &&
        (!params.get('stage') || lead.stage === params.get('stage')) &&
        (!params.has('hasPhone') || Boolean(lead.phone) === (params.get('hasPhone') === 'true')) &&
        (!q || [lead.name, lead.email, lead.notes, lead.phone].some(value => value.toLowerCase().includes(q))));
      const offset = Number(params.get('offset') || 0), limit = Number(params.get('limit') || 100);
      const stageCounts = rows.reduce((counts, lead) => ({ ...counts, [lead.stage]: (counts[lead.stage] || 0) + 1 }), {});
      return route.fulfill({ json: { leads: rows.slice(offset, offset + limit), total: rows.length, stageCounts } });
    }
    if (path.startsWith('/api/leads/') && request.method() === 'PATCH') {
      state.patches.push(data);
      if (state.failSave) return route.fulfill({ status: 503, json: { detail: 'Save unavailable' } });
      const lead = state.leads.find(row => path.endsWith(`/${row.leadId}`));
      Object.assign(lead, data);
      return route.fulfill({ json: { ok: true, lead } });
    }
    if (path === '/api/contacts/normalize-preview') {
      state.validations.push(data);
      const contacts = data.rows.map(row => ({ full_name: row.full_name, phone: row.phone, email: row.email, notes: row.notes,
        custom_fields: { lead_id: row['custom_field:lead_id'], lead_stage: row['custom_field:lead_stage'] } }));
      return route.fulfill({ json: { validCount: contacts.length, validContacts: contacts, invalidCount: 0, duplicateCount: 0, totalRows: contacts.length } });
    }
    if (path === '/api/campaigns/validate-variables') return route.fulfill({ json: { valid: true, scriptVersion: 'cb_fixture', missing_breakdown: {} } });
    if (path === '/api/campaigns' && request.method() === 'POST') {
      state.campaigns.push(data);
      return route.fulfill({ json: { campaign: { ...data, campaignId: 'lead-campaign', status: 'draft', totalContacts: data.contacts.length } } });
    }
    if (path === '/api/calls' && request.method() === 'GET') return route.fulfill({ json: { calls: [{
      call_id: 'historic-lead-call', agent_id: state.agent.id, direction: 'outbound', connected: true,
      caller_phone: '+12025550999', called_phone: '+1 (202) 555-0100', customer: 'Previous conversation',
      started_at: '2026-10-26T10:00:00Z', status: 'completed', duration_sec: 30,
    }] } });
    if (path === '/api/calls/outbound') {
      state.calls.push(data);
      if (state.failCall) return route.fulfill({ status: 503, json: { detail: 'Call unavailable' } });
      return route.fulfill({ json: { ok: true, call_id: 'lead-call' } });
    }
    return route.fallback();
  });
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await expect(page.getByTestId('lead-metric-matching-leads')).toHaveText('27');
  return state;
}

test('test call quote follows the selected stack and channel', async ({ page }) => {
  await setupVoiceWorkspace(page);
  await page.getByTestId('agent-test-call').click();
  const rate = page.getByTestId('test-call-current-rate');
  await expect(rate).toContainText('Web call rate');
  await expect(rate).toContainText('₹3.00/min');
  await page.getByTestId('test-call-mode-phone').click();
  await expect(rate).toContainText('Phone call rate');
  await page.getByTestId('test-call-mode-browser').click();
  await expect(rate).toContainText('₹3.00/min');
});

test('read-only workspace members can review leads but cannot edit them', async ({ page }) => {
  const state = await leadsFixture(page);
  await page.route('**/api/auth/me', route => route.fulfill({ json: { user: { ...state.user, role: 'customer_viewer' }, role: 'customer_viewer', tenant: { tenantId: state.user.tenantId } } }));
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await expect(page.getByRole('button', { name: 'Add lead', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Customer 00', exact: true }).first().click();
  await expect(page.getByRole('combobox', { name: 'Pipeline stage' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Save lead changes' })).toBeDisabled();
});

test('floating save dock exists only for edits and settings failure keeps the draft', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setupVoiceWorkspace(page);
  await expect(page.getByTestId('agent-save')).toHaveCount(0);
  await page.getByTestId('agent-tab-settings').click();
  await page.getByTestId('agent-settings-name').fill('Revised name');
  await expect(page.getByTestId('agent-save')).toBeVisible();
  await page.route('**/api/agents/voice-setup-agent', route => route.fulfill({ status: 503, json: { detail: 'Save unavailable' } }));
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-settings-error')).toBeVisible();
  await expect(page.getByTestId('agent-settings-name')).toHaveValue('Revised name');
  await expect(page.getByTestId('agent-save')).toBeEnabled();
  await page.unroute('**/api/agents/voice-setup-agent');
  await page.getByTestId('agent-studio-discard').click();
  await expect(page.getByTestId('agent-settings-name')).toHaveValue('Hima');
  await expect(page.getByTestId('agent-save')).toHaveCount(0);
  await page.getByTestId('agent-settings-name').fill('Confirmed new name');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-save')).toHaveCount(0);
  await expect(page.getByTestId('agent-settings-name')).toHaveValue('Confirmed new name');
});

test('full script grows and shrinks with wrapping, without an internal scrollbar', async ({ page }) => {
  await setupVoiceWorkspace(page);
  await page.getByTestId('agent-tab-script').click();
  const editor = page.getByTestId('script-textarea');
  const script = Array.from({ length: 90 }, (_, index) => `${index + 1}. Ask about the customer’s requirements and answer using approved business facts.`).join('\n');
  await editor.fill(script);
  const desktopHeight = await editor.evaluate(element => element.clientHeight);
  expect(desktopHeight).toBeGreaterThan(1800);
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await expect.poll(() => editor.evaluate(element => element.clientHeight >= element.scrollHeight - 2)).toBe(true);
    expect(await editor.evaluate(element => getComputedStyle(element).overflowY)).toBe('hidden');
    expect(await page.locator('main').evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  }
  await page.getByRole('button', { name: 'Preview with Lead', exact: true }).click();
  await page.getByRole('button', { name: 'Back to script editor' }).click();
  await expect(editor).toHaveValue(script);
  await expect.poll(() => editor.evaluate(element => element.clientHeight >= element.scrollHeight - 2)).toBe(true);
  await editor.fill('A short approved script.');
  expect(await editor.evaluate(element => element.clientHeight)).toBeLessThan(desktopHeight);
  await editor.fill(`${script}\n@cont`);
  await expect(page.getByTestId('script-variable-suggestions')).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('script-variable-suggestions')).toHaveCount(0);
});

test('voice counts follow style and gender, including empty combinations', async ({ page }) => {
  await setupVoiceWorkspace(page, { catalogVoices: 12 });
  await page.getByRole('combobox', { name: 'Voice style for low', exact: true }).selectOption('Conversational');
  const genders = page.getByRole('group', { name: 'Voice gender for low', exact: true });
  await expect(genders.getByRole('button', { name: 'All (6)', exact: true })).toBeVisible();
  await expect(genders.getByRole('button', { name: 'Male (0)', exact: true })).toBeVisible();
  await genders.getByRole('button', { name: 'Male (0)', exact: true }).click();
  await expect(page.getByTestId('voice-inventory-summary-low')).toContainText('0 Telugu voices match your filters');
  const region = page.getByRole('region', { name: 'Voices for low', exact: true });
  await expect(region.locator('[data-testid^="voice-select-btn-"]')).toHaveCount(0);
  await region.getByRole('button', { name: 'Clear voice filters' }).click();
  await expect(region.locator('[data-testid^="voice-select-btn-"]')).toHaveCount(12);
});

test('leads use server filters, accurate totals and pagination with scoped metadata', async ({ page }) => {
  const state = await leadsFixture(page);
  await expect(page.getByTestId('lead-metric-qualified')).toHaveText('14');
  await page.getByRole('button', { name: 'Next leads' }).click();
  await expect(page.getByTestId('lead-row-lead-26')).toBeVisible();
  await expect(page.getByTestId('lead-row-lead-0')).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Stage', exact: true }).selectOption('Qualified');
  await expect(page.getByTestId('lead-metric-matching-leads')).toHaveText('14');
  await page.getByRole('searchbox', { name: 'Search leads' }).fill('customer0@example.invalid');
  await expect(page.getByTestId('lead-metric-matching-leads')).toHaveText('1');
  await expect(page.getByRole('button', { name: 'Customer 00', exact: true })).toBeVisible();
  expect(state.queries.at(-1)).toContain('agentId=voice-setup-agent');
  expect(state.queries.at(-1)).toContain('stage=qualified');
  expect(state.queries.at(-1)).toContain('offset=0');
  await expect(page.getByTestId('leads-workspace')).not.toContainText(/BANT|undefined/);
  state.failList = true;
  await page.getByRole('button', { name: 'Refresh leads' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Lead service unavailable' })).toBeVisible();
  state.failList = false;
  await page.getByRole('button', { name: 'Retry leads' }).click();
  await expect(page.getByTestId('lead-metric-matching-leads')).toHaveText('1');
});

test('lead notes save once explicitly, preserve failed edits, and link to call history', async ({ page }) => {
  const state = await leadsFixture(page);
  await page.getByRole('button', { name: 'Customer 00', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('textbox', { name: 'Notes & next step' }).fill('Call Friday for an approved demo');
  await dialog.getByRole('combobox', { name: 'Pipeline stage' }).selectOption('Meeting Booked');
  expect(state.patches).toHaveLength(0);
  state.failSave = true;
  await dialog.getByRole('button', { name: 'Save lead changes' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Save unavailable');
  await expect(dialog.getByRole('textbox', { name: 'Notes & next step' })).toHaveValue('Call Friday for an approved demo');
  state.failSave = false;
  await dialog.getByRole('button', { name: 'Save lead changes' }).click();
  await expect(dialog.getByRole('button', { name: 'Save lead changes' })).toBeDisabled();
  expect(state.patches.at(-1)).toEqual({ stage: 'meeting_booked', notes: 'Call Friday for an approved demo', expectedUpdatedAt: '2026-10-27T09:00:00Z' });
  await dialog.getByRole('button', { name: 'View recent calls' }).click();
  await expect(page.getByTestId('agent-calls-panel-tab-history')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByPlaceholder(/Search/).filter({ visible: true })).toHaveValue(state.leads[0].phone);
  await expect(page.getByText('Previous conversation', { exact: true }).first()).toBeVisible();
});

test('an agent-owned lead on a later page calls the correct agent and handles a failed dial', async ({ page }) => {
  const state = await leadsFixture(page);
  await page.getByRole('button', { name: 'Next leads' }).click();
  await page.getByRole('button', { name: 'Customer 26', exact: true }).click();
  const dialog = page.getByRole('dialog');
  state.failCall = true;
  await dialog.getByRole('button', { name: 'Call lead', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Call unavailable');
  await expect(dialog.getByRole('button', { name: 'Call lead', exact: true })).toBeEnabled();
  state.failCall = false;
  await dialog.getByRole('button', { name: 'Call lead', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Call requested for Customer 26' })).toBeVisible();
  expect(state.calls.at(-1)).toMatchObject({ agentId: state.agent.id, toE164: state.leads[26].phone });
});

test('lead selections enter existing campaign validation and save a linked draft', async ({ page }) => {
  const state = await leadsFixture(page);
  await page.getByRole('checkbox', { name: 'Select Customer 00', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Select Customer 01', exact: true }).check();
  await expect(page.getByRole('checkbox', { name: 'Select Customer 02', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Create campaign (2)', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByTestId('campaign-selected-leads')).toContainText('2 selected leads');
  await dialog.getByLabel('Campaign name', { exact: true }).fill('Lead follow-up');
  await dialog.getByRole('button', { name: 'Validate contacts', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Save as draft' })).toBeDisabled();
  expect(state.validations[0].mapping['custom_field:lead_id']).toBe('custom_field:lead_id');
  await dialog.getByRole('checkbox', { name: /I confirm I have authorization/ }).check();
  await dialog.getByRole('button', { name: 'Save as draft' }).click();
  await expect(dialog).not.toBeVisible();
  expect(state.campaigns).toHaveLength(1);
  expect(state.campaigns[0]).toMatchObject({ autoStart: false, agentId: state.agent.id, consentConfirmed: true, dndScrubEnabled: true });
  expect(state.campaigns[0].contacts.map(contact => contact.custom_fields.lead_id)).toEqual(['lead-0', 'lead-1']);
});

test('lead list and detail remain usable on mobile without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await leadsFixture(page);
  await expect(page.getByRole('button', { name: 'Customer 00', exact: true }).filter({ visible: true })).toBeVisible();
  await page.getByRole('button', { name: 'Customer 00', exact: true }).filter({ visible: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../artifacts/call-quality-review/workspace-experience-20261027/leads-mobile.png' });
});

test('Converted is tenant-confirmed, counted, and filterable', async ({ page }) => {
  const state = await leadsFixture(page);
  await page.getByRole('button', { name: 'Customer 00', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Pipeline stage').selectOption('Converted');
  await expect(dialog.getByRole('button', { name: 'Save lead changes' })).toBeDisabled();
  await dialog.getByRole('checkbox', { name: 'I confirm this lead became a customer.' }).check();
  await dialog.getByRole('button', { name: 'Save lead changes' }).click();
  await expect(dialog.getByRole('button', { name: 'Save lead changes' })).toBeDisabled();
  expect(state.patches.at(-1)).toMatchObject({ stage: 'converted', confirmConverted: true });
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page.getByTestId('lead-metric-converted')).toHaveText('1');
  await page.getByRole('combobox', { name: 'Stage', exact: true }).selectOption('Converted');
  await expect(page.getByTestId('lead-metric-matching-leads')).toHaveText('1');
});
