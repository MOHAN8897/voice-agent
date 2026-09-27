import { test, expect } from '@playwright/test';
import { buildEmployee, getSessionMeta, login } from './helpers/api.js';

const E2E_EMAIL = process.env.E2E_EMAIL;
const E2E_PASSWORD = process.env.E2E_PASSWORD;

async function signInFromMarketing(page) {
  await page.goto('/');
  await page.getByRole('button', { name: /sign in/i }).first().click();
  await page.getByLabel(/work email/i).fill(E2E_EMAIL);
  await page.locator('input[type="password"]').fill(E2E_PASSWORD);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  await page.waitForTimeout(2000);
}

test.describe('Create AI employee', () => {
  test.beforeAll(async () => {
    const meta = await getSessionMeta();
    if (!meta.saas_auth_enabled) {
      test.skip(true, 'SAAS_AUTH_ENABLED is false on API');
    }
  });

  test('build-employee API returns agent and variables', async () => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    const auth = await login(E2E_EMAIL, E2E_PASSWORD);
    expect(auth.ok).toBeTruthy();
    const token = auth.data.accessToken;

    const res = await buildEmployee(token, {
      brief:
        'We are E2E Test Clinic in Hyderabad. Greet callers, book appointments, collect {{caller_name}} and callback number.',
      language: 'en-IN',
      mode: 'instant_lead',
    });
    expect(res.ok).toBeTruthy();
    expect(res.data.agentId || res.data.agent?.agent_id).toBeTruthy();
    expect(String(res.data.script || '')).toBeTruthy();
    expect(Array.isArray(res.data.variables)).toBeTruthy();
  });

  test('console modal matches craft UI and validates brief', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await page.goto('/#dashboard/employees');
    await expect(page.getByRole('heading', { name: /ai employees/i })).toBeVisible({ timeout: 20000 });

    await page.getByRole('button', { name: /create ai employee/i }).click();
    const modal = page.getByTestId('create-employee-modal');
    await expect(modal).toBeVisible();
    await expect(page.getByRole('dialog')).toContainText(/build my employee/i);

    await page.getByTestId('employee-build-submit').click();
    await expect(page.getByTestId('employee-create-error')).toContainText(/at least 8 characters/i);

    await page.getByTestId('employee-industry-clinic').click();
    await expect(page.getByTestId('employee-brief-input')).not.toHaveValue('');

    await page.getByTestId('employee-mode-bulk').click();
    await expect(page.getByTestId('employee-mode-bulk')).toHaveAttribute('aria-selected', 'true');

    await page.getByTestId('employee-lang-hi-IN').click();
    await expect(page.getByTestId('employee-natural-spoken-style')).toBeVisible();
  });

  test('full build flow opens script builder', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await page.goto('/#dashboard/employees');
    await page.getByRole('button', { name: /create ai employee/i }).click();
    await expect(page.getByTestId('create-employee-modal')).toBeVisible();

    const brief =
      'E2E Playwright agent for a dental clinic. Book cleanings and collect patient name and phone.';
    await page.getByTestId('employee-brief-input').fill(brief);
    await page.getByTestId('employee-build-submit').click();

    await expect(page.getByTestId('create-employee-modal')).toBeHidden({ timeout: 60000 });
    await expect(page.getByText(/script|opening|greeting/i).first()).toBeVisible({ timeout: 20000 });
  });
});
