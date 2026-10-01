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

/** Open the one-step creation flow. */
async function openWizard(page) {
  await page.goto('/#dashboard/employees');
  await page.getByRole('heading', { name: /ai employees/i }).waitFor({ timeout: 20000 });
  await page.getByRole('button', { name: /create ai employee/i }).click();
  await expect(page.getByTestId('create-employee-modal')).toBeVisible();
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

    // The machine-readable entity tags are a compiler/runtime contract. They belong in
    // the compiled brain, never in the script the customer reads.
    expect(res.data.script).not.toContain('ENTITY TAGS');
    expect(res.data.script).not.toContain('@agent_name');
  });

  test('asks for a brief before it will create', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await openWizard(page);

    // The next button stays disabled until there is something to compile.
    await expect(page.getByTestId('create-next')).toBeDisabled();

    await page.getByTestId('employee-industry-clinic').click();
    await expect(page.getByTestId('employee-brief-input')).not.toHaveValue('');
    await expect(page.getByTestId('create-next')).toBeEnabled();

    // Mode is a radio group now, so it reports aria-checked.
    await page.getByTestId('employee-mode-bulk').click();
    await expect(page.getByTestId('employee-mode-bulk')).toHaveAttribute('aria-checked', 'true');

    // Language and role are selects rather than chips.
    await page.getByTestId('employee-language-select').selectOption('hi-IN');
    await expect(page.getByTestId('employee-natural-spoken-style')).toBeVisible();
  });

  test('creation is a single step and lands on the agent page', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await openWizard(page);

    // There is no stepper any more — everything needed is on this one screen.
    await expect(page.getByRole('list', { name: /agent creation progress/i })).toHaveCount(0);
    await expect(page.getByTestId('employee-brief-input')).toBeVisible();
    await expect(page.getByTestId('employee-language-select')).toBeVisible();
    await expect(page.getByTestId('employee-role-select')).toBeVisible();

    await page
      .getByTestId('employee-brief-input')
      .fill(
        'E2E Playwright dental clinic in Hyderabad. Book cleanings and collect the patient name and phone.'
      );
    await page.getByTestId('employee-language-select').selectOption('en-IN');
    await page.getByTestId('create-next').click();

    // The modal closes and the agent page opens on the script, which is where the
    // rest of the settings now live.
    await expect(page.getByTestId('create-employee-modal')).toBeHidden({ timeout: 60000 });
    await expect(page.getByText(/calling script/i).first()).toBeVisible({ timeout: 20000 });
  });

  test('the generated script is readable English with no entity tags', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await openWizard(page);

    await page
      .getByTestId('employee-brief-input')
      .fill(
        'Agent name is Mohan. Business is Spandana Junior College. Call parents about junior college admission and IIT JEE coaching. Low fees.'
      );
    await page.getByTestId('employee-language-select').selectOption('en-IN');
    await page.getByTestId('create-next').click();

    await expect(page.getByTestId('create-employee-modal')).toBeHidden({ timeout: 60000 });
    const editor = page.locator('textarea').filter({ hasText: /AGENT IDENTITY/ });
    await expect(editor).toBeVisible({ timeout: 20000 });

    const script = await editor.inputValue();
    expect(script).toContain('AGENT IDENTITY');
    expect(script).toContain('CANONICAL OPENING');
    expect(script).not.toContain('ENTITY TAGS');
    expect(script).not.toContain('@agent_name');
    // An English agent must not open the call in another language.
    expect(script).not.toMatch(/[\u0900-\u097F\u0C00-\u0C7F]/);
  });

  test('call history uses the server status vocabulary', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await page.goto('/#dashboard/calls');
    await page.getByRole('heading', { name: /^calls/i }).waitFor({ timeout: 20000 });

    // Missed must be a real, selectable bucket — it is derived server-side now.
    for (const bucket of ['all', 'answered', 'missed', 'voicemail', 'outbound']) {
      await expect(page.getByTestId(`calls-status-${bucket}`)).toBeVisible();
    }
    await page.getByTestId('calls-status-missed').click();
    await expect(page.getByTestId('calls-status-missed')).toBeVisible();
  });
});
