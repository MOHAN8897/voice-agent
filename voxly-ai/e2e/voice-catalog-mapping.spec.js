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
