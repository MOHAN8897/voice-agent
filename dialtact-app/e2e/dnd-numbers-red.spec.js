import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.
// Do-not-call numbers read as blocked at a glance: full formatted number in the
// danger colour, plus a "Do not call" badge so colour is never the only signal.

const AGENT = 'voice-setup-agent';

function isRed(color) {
  const [r, g, b] = color.match(/\d+(\.\d+)?/g).map(Number);
  return r > g + 60 && r > b + 60;
}

async function setup(page) {
  await setupVoiceWorkspace(page);
  await page.route('**/api/dnc**', (route) => route.fulfill({ json: { total: 2, entries: [
    { id: 'd1', phoneE164: '+919398247132', source: 'call_opt_out', reason: 'Asked not to be called', addedAt: '2026-10-30T10:00:00Z' },
    { id: 'd2', phoneE164: '+12025550123', source: 'manual', reason: 'manual_operator', addedAt: '2026-10-29T10:00:00Z' },
  ] } }));
  await page.route('**/api/leads**', (route) => route.fulfill({ json: { total: 2, leads: [
    { id: 'lead-dnd', agentId: AGENT, name: 'Ravi', phone: '+919398247132', stage: 'contacted', doNotCall: true, updatedAt: '2026-10-30T10:00:00Z' },
    { id: 'lead-ok', agentId: AGENT, name: 'Sita', phone: '+919000000011', stage: 'new', updatedAt: '2026-10-30T09:00:00Z' },
  ] } }));
}

test('Do not call registry shows each blocked number in red with a badge', async ({ page }) => {
  await setup(page);
  await page.goto('/#dashboard/leads');
  await page.getByRole('navigation', { name: 'Lead management' }).getByRole('button', { name: 'Do not call' }).click();
  const row = page.getByTestId('dnc-row-+919398247132');
  await expect(row).toBeVisible();

  const phone = row.getByTestId('dnc-phone');
  await expect(phone).toHaveText('+91 93982 47132');
  expect(isRed(await phone.evaluate((el) => getComputedStyle(el).color))).toBe(true);
  await expect(row.getByTestId('dnc-blocked-badge')).toHaveText('Do not call');
  await expect(page.getByTestId('dnc-row-+12025550123').getByTestId('dnc-phone')).toHaveText('+1 202 555 0123');

  // Removed numbers are history, not blocked: no red and no badge.
  await page.getByTestId('dnc-tab-deactivated').click();
  const removed = page.getByTestId('dnc-row-+919398247132');
  await expect(removed.getByTestId('dnc-blocked-badge')).toHaveCount(0);
  expect(isRed(await removed.getByTestId('dnc-phone').evaluate((el) => getComputedStyle(el).color))).toBe(false);
});

test('a lead on the do-not-call list shows its number in red in the pipeline', async ({ page }) => {
  await setup(page);
  await page.goto('/#dashboard/leads');
  const blocked = page.getByText('+91 93982 47132').first();
  await expect(blocked).toBeVisible();
  expect(isRed(await blocked.evaluate((el) => getComputedStyle(el).color))).toBe(true);
  await expect(page.getByText('DND · calling blocked').first()).toBeVisible();
  const allowed = page.getByText('+91 90000 00011').first();
  expect(isRed(await allowed.evaluate((el) => getComputedStyle(el).color))).toBe(false);
});
