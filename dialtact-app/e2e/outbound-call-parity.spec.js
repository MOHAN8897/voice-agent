import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Every place that starts an outgoing call renders the same shared form
// (OutboundCallForm): agent test call → Phone call, the agent's Calls tab →
// Outgoing → Single call, and the Calls page "Place a call". The API is mocked;
// no call is placed.

const LINES = ['+918041230001', '+918041230002'];
const UNAVAILABLE = "We couldn't start this call because the voice service is temporarily unavailable. You weren't charged. Please try again in a few minutes.";

async function setup(page, { outbound = 'ok' } = {}) {
  const base = await setupVoiceWorkspace(page);
  const agentId = base.agent.id;
  const state = { dials: [] };
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path === '/api/telephony/numbers') {
      return route.fulfill({ json: { numbers: LINES.map((e164, i) => ({ id: `line-${i}`, e164, agentId: i === 0 ? agentId : null, status: 'active' })) } });
    }
    if (path === '/api/integrations/call-options') {
      return route.fulfill({ json: { items: [{ app: 'hubspot', name: 'HubSpot', selectable: true, defaultMode: 'after_call',
        modes: [{ mode: 'after_call', label: 'After the call', description: 'Logs the call to HubSpot.' }] }] } });
    }
    if (path === '/api/calls/outbound') {
      state.dials.push(req.postDataJSON());
      if (outbound === 'unavailable') {
        return route.fulfill({ status: 503, headers: { 'Retry-After': '120' }, json: { detail: { error: {
          code: 'voice_service_unavailable', message: UNAVAILABLE, retryable: true, retry_after: 120 } } } });
      }
      return route.fulfill({ json: { ok: true, callId: 'call-1' } });
    }
    return route.fallback();
  });
  return { ...base, agentId, state };
}

async function openTestCallPhone(page, agentId) {
  await page.goto(`/#dashboard/employees?step=voice&agent=${agentId}`);
  await page.getByTestId('agent-test-call').click();
  await page.getByTestId('test-call-mode-phone').click();
  await expect(page.getByTestId('test-call-live-number')).toBeVisible();
}

async function openOutgoing(page, agentId) {
  await page.goto(`/#dashboard/employees?step=calls&agent=${agentId}`);
  await page.getByTestId('agent-calls-panel-tab-outbound').click();
  await expect(page.getByTestId('agent-dial-bulk')).toBeVisible();
}

/** The options a tenant gets, read off whichever form is on screen. */
async function formOptions(form) {
  return {
    from: await form.locator('[data-outbound-field="from"] option').allTextContents(),
    to: await form.locator('[data-outbound-field="to"]').count(),
    apps: await form.getByTestId('ci-toggle-hubspot').count(),
    summary: (await form.getByText('This call will use').count()) > 0,
  };
}

test('the test-call phone form offers everything Outgoing → Single call offers', async ({ page }, testInfo) => {
  const { agentId } = await setup(page);
  await openOutgoing(page, agentId);
  const outgoing = await formOptions(page.getByTestId('agent-dial-form'));
  await page.getByTestId('agent-dial-bulk').screenshot({ path: testInfo.outputPath('outgoing-single-call.png') });
  await openTestCallPhone(page, agentId);
  const phoneTest = await formOptions(page.getByTestId('test-call-phone-form'));
  await page.getByTestId('test-call-live-number').screenshot({ path: testInfo.outputPath('test-call-phone-form.png') });
  expect(phoneTest).toEqual(outgoing);
  expect(outgoing.from).toHaveLength(3);
  expect(outgoing.apps).toBe(1);
  // The agent's own line is the default caller ID in both.
  await expect(page.getByTestId('test-call-phone-from-select')).toHaveValue(LINES[0]);
});

test('the phone test sends the chosen line, number and apps like the Outgoing tab', async ({ page }) => {
  const { agentId, state } = await setup(page);
  await openTestCallPhone(page, agentId);
  await page.getByTestId('test-call-phone-from-select').selectOption(LINES[1]);
  await page.getByTestId('test-call-phone-to').fill('98765 43210');
  await page.getByTestId('ci-toggle-hubspot').check();
  await page.getByTestId('test-call-start-phone').click();
  await expect.poll(() => state.dials.length).toBe(1);
  expect(state.dials[0]).toMatchObject({ agentId, toE164: '+919876543210', fromE164: LINES[1], integrations: [{ app: 'hubspot', mode: 'after_call' }] });
  expect(state.dials[0].dialRequestId).toBeTruthy();
  await expect(page.getByText('Dialing +919876543210…')).toBeVisible();
  await expect(page.getByTestId('test-call-phone-to')).toHaveValue('');
});

test('the same validation and voice-service copy appear in every dialer', async ({ page }) => {
  const { agentId, state } = await setup(page, { outbound: 'unavailable' });

  // Invalid number: refused before any request, same sentence everywhere.
  await openOutgoing(page, agentId);
  await page.getByTestId('agent-dial-to').fill('12ab');
  await page.getByTestId('agent-dial-start').click();
  await expect(page.getByTestId('agent-dial-bulk-error')).toHaveText('Use digits and a country code, such as +91.');

  await openTestCallPhone(page, agentId);
  await page.getByTestId('test-call-phone-to').fill('12ab');
  await page.getByTestId('test-call-start-phone').click();
  await expect(page.getByTestId('test-call-phone-error')).toHaveText('Use digits and a country code, such as +91.');
  expect(state.dials).toHaveLength(0);

  // A vendor outage: the server's tenant sentence, not "HTTP 503" or a banner.
  await page.getByTestId('test-call-phone-to').fill('+919876543210');
  await page.getByTestId('test-call-start-phone').click();
  await expect(page.getByTestId('test-call-phone-error')).toHaveText(UNAVAILABLE);
  await expect(page.getByText(`Call attempt failed: ${UNAVAILABLE}`)).toBeVisible();

  await page.keyboard.press('Escape');
  await page.getByTestId('nav-calls').click();
  await page.getByRole('tab', { name: 'Place a call' }).click();
  await page.getByTestId('calls-place-call-to').fill('+919876543210');
  await page.getByTestId('calls-place-call-submit').click();
  await expect(page.getByTestId('calls-place-call-error')).toHaveText(UNAVAILABLE);
  // The Calls page form is the same form, plus the agent picker.
  const callsForm = page.getByTestId('calls-place-call-form');
  await expect(callsForm.locator('[data-outbound-field="agent"]')).toBeVisible();
  await expect(callsForm.getByTestId('ci-toggle-hubspot')).toBeVisible();
  expect(state.dials).toHaveLength(2);
});

test('the phone test keeps its draft when the modal is closed and reopened', async ({ page }) => {
  const { agentId } = await setup(page);
  await openTestCallPhone(page, agentId);
  await page.getByTestId('test-call-phone-from-select').selectOption(LINES[1]);
  await page.getByTestId('test-call-phone-to').fill('+919812345678');
  await page.keyboard.press('Escape');
  await page.getByTestId('agent-test-call').click();
  await page.getByTestId('test-call-mode-phone').click();
  await expect(page.getByTestId('test-call-phone-to')).toHaveValue('+919812345678');
  await expect(page.getByTestId('test-call-phone-from-select')).toHaveValue(LINES[1]);
});
