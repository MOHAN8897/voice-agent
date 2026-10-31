import { test, expect } from '@playwright/test';

import { setupClarification } from './helpers/clarification.js';

test('asks grouped questions and a follow-up, then uses all answers to create once', async ({ page }) => {
  const state = await setupClarification(page);
  await page.getByTestId('employee-brief-input').fill('Create a sales agent for Example online courses.');
  await page.getByTestId('employee-language-select').selectOption('en-IN');
  await page.getByTestId('create-next').click();
  await expect(page.getByRole('dialog', { name: 'A few details for your employee' })).toBeVisible();
  await expect(page.getByTestId('create-next')).toBeDisabled();
  expect(state.builds).toHaveLength(0);
  await page.getByTestId('employee-answer-agent_name').fill('Meera');
  await page.getByTestId('employee-answer-offer').fill('An online course costs INR 500. Access is by email after purchase.');
  await page.getByTestId('employee-unknown-refund_policy').check();
  await page.getByTestId('create-next').click();
  await expect(page.getByTestId('employee-answer-next_step')).toBeFocused();
  expect(state.builds).toHaveLength(0);
  await page.getByTestId('employee-answer-next_step').fill('Tell them to buy through the official website; do not collect payment on calls.');
  await page.getByTestId('create-next').click();
  await expect(page.getByTestId('create-employee-modal')).toBeHidden();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  expect(state.builds).toHaveLength(1);
  const answers = state.builds[0].clarificationAnswers;
  expect(answers).toHaveLength(4);
  expect(answers.find((item) => item.field === 'refund_policy')).toMatchObject({ unavailable: true, answer: '' });
  expect(answers.find((item) => item.field === 'offer').answer).toContain('INR 500');
  await expect(page.getByTestId('review-script-btn')).toHaveCount(0);
  await expect(page.getByTestId('script-review-result')).toHaveCount(0);
  await expect(page.getByTestId('agent-script-generation-status')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('private-version-must-not-display');
});

test('analysis failures preserve the brief and recover without creating an agent', async ({ page }) => {
  const state = await setupClarification(page, { failAnalysis: true });
  const brief = 'Create a sales agent for Example online courses.';
  await page.getByTestId('employee-brief-input').fill(brief);
  await page.getByTestId('create-next').click();
  await expect(page.getByTestId('employee-create-error')).toContainText('could not check the brief');
  await expect(page.getByTestId('employee-brief-input')).toHaveValue(brief);
  expect(state.builds).toHaveLength(0);
  state.failAnalysis = false;
  await page.getByTestId('create-next').click();
  await expect(page.getByTestId('employee-answer-agent_name')).toBeVisible();
});

test('keyboard stays in the modal and answers survive a failed recheck', async ({ page }) => {
  const state = await setupClarification(page);
  await page.getByTestId('employee-brief-input').fill('Create a sales agent for Example online courses.');
  await page.getByTestId('create-next').click();
  await page.getByTestId('employee-answer-agent_name').fill('Meera');
  await page.getByTestId('employee-answer-offer').fill('An online course costs INR 500.');
  await page.getByTestId('employee-unknown-refund_policy').check();
  state.failAnalysis = true;
  await page.getByTestId('create-next').click();
  await expect(page.getByTestId('employee-create-error')).toBeVisible();
  await expect(page.getByTestId('employee-answer-offer')).toHaveValue('An online course costs INR 500.');
  await expect(page.getByTestId('employee-unknown-refund_policy')).toBeChecked();
  await page.getByTestId('create-next').focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Close dialog' })).toBeFocused();
  expect(state.builds).toHaveLength(0);
});
