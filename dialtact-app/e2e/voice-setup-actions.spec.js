import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

test('tier selection saves immediately while the script save dock stays hidden without edits', async ({ page }) => {
  const state = await setupVoiceWorkspace(page);
  await expect(page.getByTestId('voice-stack-tier-low')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Test Live Agent', exact: true })).toHaveCount(0);
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toHaveCount(0);
  await page.getByTestId('voice-stack-tier-low').check();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
  await expect(page.getByTestId('agent-studio-unsaved')).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0]).toMatchObject({ defaultTier: 'low', expectedVoiceRevision: 1, voiceSettings: {
    profileRevision: 2, engineId: 'engine-low', modelId: 'model-low', voiceId: 'voice-low',
  } });
  await page.getByTestId('agent-test-call').click();
  await expect(page.getByTestId('agent-test-call-panel')).toBeVisible();
});

test('Flagship profile preserves the chosen model and voice aliases', async ({ page }) => {
  const state = await setupVoiceWorkspace(page);
  await page.getByTestId('voice-stack-tier-premium').check();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  expect(state.writes[0].voiceSettings).toEqual({ stackSelectionVersion: 1, profileRevision: 4,
    engineId: 'engine-premium', modelId: 'model-premium', voiceId: 'voice-premium' });
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
});

test('a saved voice stays valid after an admin bumps the profile revision', async ({ page }) => {
  // The server keeps a saved choice while its aliases still resolve
  // (resolve_agent_selection); the console must not call it lost.
  await setupVoiceWorkspace(page, { staleSelection: true });
  await expect(page.getByTestId('voice-select-btn-voice-medium')).toContainText('Selected');
  await expect(page.getByTestId('voice-setup-needs-selection')).toHaveCount(0);
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
});

test('a saved voice removed from the catalog blocks tests until a current voice is saved', async ({ page }) => {
  await setupVoiceWorkspace(page, { removedVoice: true });
  await expect(page.getByTestId('voice-setup-needs-selection')).toBeVisible();
  await expect(page.getByTestId('agent-test-call')).toBeDisabled();
  await page.getByTestId('voice-select-btn-voice-medium').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  await expect(page.getByTestId('agent-test-call')).toBeEnabled();
});

test('failed voice save retains the previous selection and blocks testing the draft', async ({ page }) => {
  const state = await setupVoiceWorkspace(page, { failSave: true });
  await page.getByTestId('voice-stack-tier-low').check();
  await expect(page.getByTestId('voice-stack-save-error')).toBeVisible();
  await expect(page.getByTestId('agent-test-call')).toBeDisabled();
  expect(state.agent.defaultTier).toBe('medium');
});
