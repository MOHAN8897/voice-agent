import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

test('all language-matched voices scroll and retain numbered identity across provider style filters', async ({ page }) => {
  const state = await setupVoiceWorkspace(page, { catalogVoices: 60 });
  const region = page.getByRole('region', { name: 'Voices for low', exact: true });
  await expect(region.getByTestId('voice-select-btn-voice-low-60')).toBeAttached();
  expect(await region.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  await expect(region).toHaveAttribute('tabindex', '0');
  await page.getByRole('combobox', { name: 'Voice style for low', exact: true }).selectOption('Conversational');
  await expect(region.getByTestId('voice-select-btn-voice-low-1')).toHaveCount(0);
  await expect(region.getByText('Voice 60', { exact: true })).toBeAttached();
  await region.getByTestId('voice-select-btn-voice-low-60').scrollIntoViewIfNeeded();
  await region.getByTestId('voice-select-btn-voice-low-60').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  expect(state.writes.at(-1).voiceSettings).toMatchObject({ engineId: 'engine-low', modelId: 'model-low', voiceId: 'voice-low-60' });
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
});

test('every provider voice reaches the tenant for a supported language without exposing providers', async ({ page }) => {
  const state = await setupVoiceWorkspace(page, { catalogVoices: 12 });
  state.profiles[0].voiceInventory = { totalVoices: 12, voicesByLanguage: { 'te-IN': 12 } };
  await page.getByTestId('refresh-voice-stacks-btn').click();
  const summary = page.getByTestId('voice-inventory-summary-low');
  await expect(summary).toContainText('12 Telugu voices match your filters');
  const region = page.getByRole('region', { name: 'Voices for low', exact: true });
  await expect(region.locator('[data-testid^="voice-select-btn-"]')).toHaveCount(12);
  await expect(page.getByTestId('voice-stack-selector')).not.toContainText(/sarvam|bulbul|telnyx|vobiz|nango/i);
});

test('catalogue refresh awaits requests and reports a failed catalogue instead of success', async ({ page }) => {
  await setupVoiceWorkspace(page);
  const refresh = page.getByTestId('refresh-voice-stacks-btn');
  await expect(refresh).toBeVisible();
  await page.route('**/api/voice-stacks/catalog*', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
  });
  await refresh.click();
  await expect(page.getByTestId('voice-stack-loading')).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: 'Approved voice options could not be loaded' })).toBeVisible();
  await expect(page.getByText('Some voice options could not be refreshed. Check the catalogue messages and retry.', { exact: true })).toBeVisible();
  await expect(page.getByText('Voice options refreshed.', { exact: true })).toHaveCount(0);
});
