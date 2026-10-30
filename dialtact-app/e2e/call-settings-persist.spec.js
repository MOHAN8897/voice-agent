import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// What a tenant picks on the Calls pages must survive moving around the console.
// Drafts (line, number to call, integrations, campaign options, the sub-tab) live
// in this browser tab's sessionStorage until the call is placed; saved incoming
// rules come from the server and must never be replaced by built-in defaults.
// The API is mocked; no call is placed.

const CSV = ['phone,full_name', '+919800000001,Asha'].join('\n');
const LINES = ['+918041230001', '+918041230002'];

async function setup(page, { profileStatus = 200 } = {}) {
  const base = await setupVoiceWorkspace(page);
  const agentId = base.agent.id;
  const state = { dials: [] };
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path === '/api/telephony/numbers') {
      return route.fulfill({ json: { numbers: LINES.map((e164, i) => ({ id: `line-${i}`, e164, agentId, status: 'active' })) } });
    }
    if (path === '/api/integrations/call-options') {
      return route.fulfill({ json: { items: [{ app: 'hubspot', name: 'HubSpot', selectable: true, defaultMode: 'after_call',
        modes: [{ mode: 'after_call', label: 'After the call', description: 'Logs the call to HubSpot.' }] }] } });
    }
    if (path.endsWith('/telephony-profile/effective')) {
      return route.fulfill({ json: { decision: { afterHours: false, reason: 'in_hours' }, hasProfile: true, timezone: 'Asia/Kolkata' } });
    }
    if (path.endsWith('/telephony-profile')) {
      if (profileStatus !== 200) return route.fulfill({ status: profileStatus, json: { detail: 'Operating settings unavailable' } });
      return route.fulfill({ json: { profile: {
        agentId, greetingPhrase: '', timezone: 'Asia/Kolkata', afterHoursAction: 'transfer', transferNumber: '+919800000000',
        businessHours: { mon: [{ start: '09:00', end: '17:00' }] }, closedDates: [], inboundEnabled: true, outboundEnabled: true, hasProfile: true,
      }, afterHoursActions: ['voicemail', 'hangup', 'transfer', 'always'] } });
    }
    if (path.includes('/calls/outbound') || path.endsWith('/telephony/call')) {
      state.dials.push(req.postDataJSON());
      return route.fulfill({ json: { ok: true, callId: 'call-1' } });
    }
    return route.fallback();
  });
  const workspace = `/#dashboard/employees?step=calls&agent=${agentId}`;
  await page.goto(workspace);
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  return { ...base, state, workspace };
}

async function openOutgoing(page) {
  await page.getByTestId('agent-calls-panel-tab-outbound').click();
  await expect(page.getByTestId('agent-dial-bulk')).toBeVisible();
}

test('outgoing call choices survive sub-tab and page switches', async ({ page }) => {
  const { workspace } = await setup(page);
  await openOutgoing(page);
  await expect(page.getByTestId('agent-dial-from').locator('option')).toHaveCount(3);
  await page.getByTestId('agent-dial-from').selectOption(LINES[1]);
  await page.getByTestId('agent-dial-to').fill('+919876543210');
  await page.getByTestId('ci-toggle-hubspot').check();
  await expect(page.getByTestId('agent-dial-integration-summary')).toContainText('HubSpot');

  // Another sub-tab and back.
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await expect(page.getByTestId('agent-inbound-panel')).toBeVisible();
  await openOutgoing(page);
  await expect(page.getByTestId('agent-dial-from')).toHaveValue(LINES[1]);
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('+919876543210');
  await expect(page.getByTestId('ci-toggle-hubspot')).toBeChecked();

  // Another workspace tab and back: the Outgoing sub-tab itself is remembered.
  await page.getByTestId('agent-tab-overview').click();
  await page.getByTestId('agent-tab-calls').click();
  await expect(page.getByTestId('agent-calls-panel-tab-outbound')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('+919876543210');

  // Another page and back.
  await page.getByTestId('nav-phone-numbers').click();
  await expect(page).toHaveURL(/phone-numbers/);
  await page.goto(workspace);
  await expect(page.getByTestId('agent-calls-panel-tab-outbound')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('agent-dial-from')).toHaveValue(LINES[1]);
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('+919876543210');
  await expect(page.getByTestId('ci-toggle-hubspot')).toBeChecked();

  // A reload in the same tab keeps the draft too (sessionStorage, never localStorage).
  await page.reload();
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('+919876543210');
  const leaked = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('dialtact_draft:')));
  expect(leaked).toEqual([]);
});

test('bulk campaign options survive switching away and back', async ({ page }) => {
  const { workspace } = await setup(page);
  await openOutgoing(page);
  await page.getByTestId('agent-outbound-tab-bulk').click();
  const setup_ = page.getByTestId('campaign-setup');
  await setup_.getByLabel('Campaign name', { exact: true }).fill('Diwali follow-up');
  await setup_.getByRole('button', { name: 'Paste CSV', exact: true }).click();
  await setup_.getByLabel('CSV contacts').fill(CSV);

  await page.getByTestId('agent-calls-panel-tab-history').click();
  await page.getByTestId('nav-calls').click();
  await page.goto(workspace);
  await expect(page.getByTestId('agent-calls-panel-tab-outbound')).toHaveAttribute('aria-selected', 'false');
  await openOutgoing(page);
  await expect(page.getByTestId('campaign-setup')).toBeVisible();
  await expect(setup_.getByLabel('Campaign name', { exact: true })).toHaveValue('Diwali follow-up');
  await expect(setup_.getByRole('button', { name: 'Paste CSV', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(setup_.getByLabel('CSV contacts')).toHaveValue(CSV);
});

test('incoming tab shows the saved rules after switching away and back', async ({ page }) => {
  const { workspace } = await setup(page);
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  const rules = page.getByTestId('agent-inbound-rules');
  await expect(rules).toContainText('Transfer to +919800000000');
  await expect(page.getByTestId('agent-inbound-panel')).toContainText('Timezone: Asia/Kolkata');
  await page.getByTestId('agent-calls-panel-tab-outbound').click();
  await page.getByTestId('nav-calls').click();
  await page.goto(workspace);
  await expect(page.getByTestId('agent-calls-panel-tab-inbound')).toHaveAttribute('aria-selected', 'false');
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await expect(rules).toContainText('Transfer to +919800000000');
});

test('incoming tab never shows default rules in place of saved ones it could not read', async ({ page }) => {
  await setup(page, { profileStatus: 503 });
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await expect(page.getByTestId('agent-inbound-load-error')).toBeVisible();
  await expect(page.getByTestId('agent-inbound-rules')).toHaveCount(0);
  await expect(page.getByTestId('agent-inbound-panel')).not.toContainText('America/New_York');
  await expect(page.getByTestId('agent-inbound-panel')).not.toContainText('Say goodbye and hang up');
});

test('Calls page "Place a call" keeps its draft across pages', async ({ page }) => {
  await setup(page);
  await page.getByTestId('nav-calls').click();
  await page.getByRole('tab', { name: 'Place a call' }).click();
  const card = page.getByRole('main');
  await card.getByLabel('Call from').selectOption(LINES[0]);
  await card.getByLabel('Number to call').fill('+919812345678');
  await page.getByTestId('ci-toggle-hubspot').check();

  await page.getByTestId('nav-phone-numbers').click();
  await expect(page).toHaveURL(/phone-numbers/);
  await page.getByTestId('nav-calls').click();
  await expect(page.getByRole('tab', { name: 'Place a call' })).toHaveAttribute('aria-selected', 'true');
  await expect(card.getByLabel('Call from')).toHaveValue(LINES[0]);
  await expect(card.getByLabel('Number to call')).toHaveValue('+919812345678');
  await expect(page.getByTestId('ci-toggle-hubspot')).toBeChecked();
});

test('saved agent settings survive a reload', async ({ page }) => {
  // Saved settings are server state: after a reload the incoming tab shows what the
  // server holds (the mocked saved profile), not defaults or the last draft.
  const { workspace } = await setup(page);
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await expect(page.getByTestId('agent-inbound-rules')).toContainText('Transfer to +919800000000');
  await page.reload();
  await page.goto(workspace);
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await expect(page.getByTestId('agent-inbound-rules')).toContainText('Transfer to +919800000000');
});

test('a placed call clears the number and per-call apps but keeps the line', async ({ page }) => {
  const { state } = await setup(page);
  await openOutgoing(page);
  await page.getByTestId('agent-dial-from').selectOption(LINES[1]);
  await page.getByTestId('agent-dial-to').fill('+919876543210');
  await page.getByTestId('ci-toggle-hubspot').check();
  await page.getByTestId('agent-dial-start').click();
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('');
  expect(state.dials).toHaveLength(1);
  expect(state.dials[0]).toMatchObject({ toE164: '+919876543210', fromE164: LINES[1], integrations: [{ app: 'hubspot', mode: 'after_call' }] });
  await expect(page.getByTestId('ci-toggle-hubspot')).not.toBeChecked();
  await page.getByTestId('agent-calls-panel-tab-inbound').click();
  await openOutgoing(page);
  await expect(page.getByTestId('agent-dial-to')).toHaveValue('');
  await expect(page.getByTestId('agent-dial-from')).toHaveValue(LINES[1]);
});
