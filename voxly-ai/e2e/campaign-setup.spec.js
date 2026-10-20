import { test, expect } from '@playwright/test';

import { setupCampaign } from './fixtures/campaign.js';

async function fillContacts(page) {
  await page.getByRole('button', { name: 'New campaign', exact: true }).click();
  await page.getByLabel('Campaign name', { exact: true }).fill('October follow-up');
  await page.getByRole('button', { name: 'Paste CSV', exact: true }).click();
  await page.getByLabel('CSV contacts', { exact: true }).fill('phone,full_name\n' + Array.from({ length: 121 }, (_, i) => `+1202555${String(100 + i).padStart(4, '0')},Example ${i}`).join('\n'));
  await page.getByRole('button', { name: 'Validate contacts', exact: true }).click();
  await expect(page.getByText('121 ready · 0 invalid · 0 duplicates')).toBeVisible();
}

for (const [name, width, height] of [['mobile', 390, 844], ['tablet', 820, 1180], ['desktop', 1440, 1000]]) {
  test(`one-page setup validates every row and launches once at ${name} size`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    const state = await setupCampaign(page);
    await fillContacts(page);
    expect(state.validations[0].rows).toHaveLength(121);
    expect(state.variableChecks[0].contacts).toHaveLength(121);
    await expect(page.getByRole('button', { name: 'Launch campaign', exact: true })).toBeDisabled();
    await page.getByRole('checkbox', { name: /I confirm I have authorization/ }).check();
    await expect(page.getByRole('button', { name: 'Launch campaign', exact: true })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const dialog = page.getByRole('dialog');
    const box = await dialog.boundingBox(); expect(box.width).toBeLessThanOrEqual(width);
    await page.getByRole('button', { name: 'Launch campaign', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    expect(state.creates).toHaveLength(1);
    expect(state.creates[0].contacts).toHaveLength(121);
    expect(state.creates[0].consentConfirmed).toBe(true);
    expect(state.creates[0].callingWindow).toEqual({ start: '09:00', end: '18:00', timezone: 'Asia/Kolkata' });
    expect(errors).toEqual([]);
  });
}

test('failed create preserves input and keyboard focus stays inside modal', async ({ page }) => {
  const state = await setupCampaign(page, { failCreate: true });
  await fillContacts(page);
  const dialog = page.getByRole('dialog');
  await page.getByRole('checkbox', { name: /I confirm I have authorization/ }).check();
  await page.getByRole('button', { name: 'Launch campaign', exact: true }).click();
  await expect(dialog.getByRole('alert')).toBeVisible();
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveValue('October follow-up');
  expect(state.creates).toHaveLength(1);
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'New campaign', exact: true })).toBeFocused();
});

test('changing import country invalidates prior validation and consent', async ({ page }) => {
  await setupCampaign(page); await fillContacts(page);
  await page.getByRole('checkbox', { name: /I confirm I have authorization/ }).check();
  await page.getByLabel('Country for local numbers').selectOption('US');
  await expect(page.getByRole('button', { name: 'Launch campaign', exact: true })).toBeDisabled();
  await expect(page.getByRole('checkbox', { name: /I confirm I have authorization/ })).not.toBeChecked();
});

test('dashboard follows server completion and bounds statistics request concurrency', async ({ page }) => {
  const initialCampaigns = Array.from({ length: 9 }, (_, n) => ({ id: `audit-${n}`, name: `Batch ${n}`, status: 'running', agentId: 'campaign-agent', totalContacts: 121 }));
  const state = await setupCampaign(page, { initialCampaigns, analyticsStatus: 'completed', analyticsDelay: 60 });
  await expect(page.getByText('completed', { exact: true })).toHaveCount(9);
  await expect(page.getByRole('button', { name: 'Pause campaign', exact: true })).toHaveCount(0);
  expect(state.analyticsRequests).toBe(9);
  expect(state.analyticsPeak).toBeLessThanOrEqual(4);
});
