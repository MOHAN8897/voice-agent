import { test, expect } from '@playwright/test';
import { setupPrimaryCall } from './fixtures/primary-call.js';

test('live caller transcript displays partial speech, final text and recognizer status', async ({ page }) => {
  const state = await setupPrimaryCall(page);
  await expect(page.getByText('Session Cost Breakdown', { exact: true })).toHaveCount(0);
  await expect(page.getByText('$0.14', { exact: true })).toBeVisible();
  state.transcription = { mode: 'live', status: 'streaming', partial_text: 'రేపు appointment', segments: 0 };
  await expect(page.getByText('Live transcription: Listening', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel('Caller speech in progress')).toContainText('రేపు appointment');
  state.transcript.push({ role: 'user', text: 'రేపు appointment ఉందా?' });
  state.transcription = { mode: 'live', status: 'complete', partial_text: '', segments: 1 };
  await expect(page.getByText('రేపు appointment ఉందా?', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('Live transcription: Complete', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Caller speech in progress')).toHaveCount(0);
  state.transcription = { mode: 'live', status: 'failed', partial_text: '', segments: 1 };
  await expect(page.getByText('Live transcription: Partial — saved transcript available', { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('Live transcription: Unavailable — contact support', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/saaras|gpt-transcribe|api\.sarvam|vobiz/i)).toHaveCount(0);
  await page.screenshot({ path: '../artifacts/pstn-live-transcription.png', fullPage: true });
  if (process.env.RETICLE_TRANSCRIPTION_HOLD === '1') {
    test.setTimeout(90000);
    await page.waitForTimeout(55000);
  }
});

test('workspace search has no keyboard shortcut hint', async ({ page }) => {
  await setupPrimaryCall(page);
  await expect(page.getByRole('button', { name: 'Search workspace', exact: true })).toBeVisible();
  await expect(page.getByText('Ctrl K', { exact: true })).toHaveCount(0);
  await expect(page.getByText('⌘K', { exact: true })).toHaveCount(0);
});

test('billing shows one wallet charge for the call without supplier cost details', async ({ page }) => {
  await setupPrimaryCall(page);
  await page.goto('/#dashboard/billing');
  await expect(page.getByText('Last call (1m 20s)', { exact: true })).toBeVisible();
  await expect(page.getByText('$0.14 billed', { exact: true })).toBeVisible();
  await expect(page.getByText(/Gemini Live AI Voice|Total Supplier Cost|Session Cost Breakdown/)).toHaveCount(0);
  await expect(page.getByText('-$0.14', { exact: true })).toBeVisible();
});

test('compact call status filter uses server statuses and refreshes live transcript and recording', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = await setupPrimaryCall(page);
  const status = page.getByRole('combobox', { name: 'Call status' });
  await expect(status).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toHaveText('Calls');
  await expect(page.getByText('Hello, how can I help?', { exact: true })).toBeVisible();
  state.transcript.push({ role: 'user', text: 'సాయంత్రం కాల్ చేయండి.' });
  await expect(page.getByText('సాయంత్రం కాల్ చేయండి.', { exact: true })).toBeVisible({ timeout: 10000 });
  state.calls[0].status = 'outbound';
  state.calls[0].has_recording = true;
  state.calls[0].end_reason = 'agent_hangup';
  await expect(page.getByTestId('call-recording-toggle')).toBeVisible({ timeout: 10000 });
  await page.getByTestId('call-recording-toggle').click();
  await expect.poll(() => state.recordings.length).toBe(1);
  await expect.poll(() => page.locator('audio').evaluate(el => el.readyState)).toBeGreaterThanOrEqual(2);
  expect(await page.locator('audio').evaluate(el => el.error?.code ?? null)).toBeNull();
  expect(state.recordings[0].authorization).toMatch(/^Bearer /);
  await status.selectOption('missed');
  await expect.poll(() => state.filters.at(-1)).toBe('missed');
  await status.selectOption('outbound');
  await expect.poll(() => state.filters.at(-1)).toBe('outbound');
  await expect(page.getByText('Recording is not available yet', { exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
  await page.screenshot({ path: '../artifacts/pstn-call-history-desktop.png', fullPage: true });
  if (process.env.RETICLE_HOLD === '1') await page.waitForTimeout(55000);
});

test('phone test handles provider rejection as an error and sends the chosen caller ID', async ({ page }) => {
  const state = await setupPrimaryCall(page);
  await page.goto('/#dashboard/employees?step=script&agent=primary-call-agent');
  await page.getByTestId('agent-test-call').click();
  await page.getByTestId('test-call-mode-phone').click();
  await expect(page.getByLabel('Call from', { exact: true })).toBeVisible();
  await page.getByLabel('Phone number to call', { exact: true }).fill('+1 (202) 555-0181');
  await page.getByTestId('test-call-start-phone').click();
  await expect.poll(() => state.dials.length).toBe(1);
  expect(state.dials[0]).toMatchObject({ agentId: 'primary-call-agent', toE164: '+12025550181', fromE164: '+12025550123' });
  await expect(page.getByText(/Call attempt failed: The agent could not get ready/)).toBeVisible();
  await expect(page.getByText('Live call initiated', { exact: true })).toHaveCount(0);
});

test('phone test blocks dialing without an eligible line and fits a mobile screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setupPrimaryCall(page, { phoneLines: false });
  await page.goto('/#dashboard/employees?step=script&agent=primary-call-agent');
  await page.getByTestId('agent-test-call').click();
  await page.getByTestId('test-call-mode-phone').click();
  await expect(page.getByTestId('test-call-start-phone')).toBeDisabled();
  await expect(page.getByText('None of your numbers can make outgoing calls yet')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/pstn-phone-test-mobile.png', fullPage: true });
});
