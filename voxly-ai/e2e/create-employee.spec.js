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

/** Open the four-step creation flow. */
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
  });

  test('step 1 asks for a brief before it will continue', async ({ page }) => {
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

  test('all four steps are shown and reachable in order', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await openWizard(page);

    for (const step of ['brief', 'script', 'configure', 'ready']) {
      await expect(page.getByTestId(`create-step-${step}`)).toBeVisible();
    }
    // Only the first step is active before anything is created.
    await expect(page.getByTestId('create-step-brief')).toHaveAttribute('aria-current', 'step');
  });

  test('full flow compiles a script, shows it, then configures the phone', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await signInFromMarketing(page);
    await openWizard(page);

    // ---- Step 1: describe
    await page
      .getByTestId('employee-brief-input')
      .fill(
        'E2E Playwright dental clinic in Hyderabad. Book cleanings and collect the patient name and phone.'
      );
    await page.getByTestId('create-next').click();

    // ---- Step 2: review the generated script. The modal stays open, because
    // the user is meant to see and edit what the agent will actually say.
    await expect(page.getByTestId('create-step-script')).toHaveAttribute('aria-current', 'step', {
      timeout: 60000,
    });
    const script = page.getByTestId('script-preview');
    await expect(script).toBeVisible();
    await expect(script).not.toBeEmpty();

    // The brief the agent was built from is shown alongside it.
    await expect(page.getByText(/built from your description/i)).toBeVisible();

    // Editing must stick.
    await page.getByTestId('script-toggle-edit').click();
    await page
      .getByTestId('script-editor')
      .fill('Greet the caller. Ask for the patient name. Book the next slot. Repeat the time back.');
    await expect(page.getByTestId('script-editor')).toHaveValue(/book the next slot/i);
    await page.getByTestId('create-next').click();

    // ---- Step 3: phone and voice
    await expect(page.getByTestId('create-step-configure')).toHaveAttribute('aria-current', 'step');
    await expect(page.getByTestId('config-inbound-enabled')).toBeVisible();
    await expect(page.getByTestId('config-outbound-enabled')).toBeVisible();

    // Business hours are a real schedule, not a free-text field.
    await expect(page.getByTestId('config-hours-summary')).toBeVisible();
    await page.getByTestId('config-day-mon').click();
    await expect(page.getByTestId('config-hours-mon-open')).toBeVisible();

    // After-hours behaviour is an explicit choice.
    await page.getByTestId('config-after-hours-voicemail').click();
    await expect(page.getByTestId('config-after-hours-voicemail')).toHaveAttribute('aria-pressed', 'true');

    // The greeting the caller hears is a real field.
    await page.getByTestId('config-greeting').fill('Thanks for calling the clinic.');

    // Switch inbound off and back on to prove the toggles are wired.
    await page.getByTestId('config-inbound-enabled').uncheck();
    await expect(page.getByTestId('config-inbound-enabled')).not.toBeChecked();
    await page.getByTestId('config-inbound-enabled').check();

    await page.getByTestId('create-next').click();

    // ---- Step 4: ready, with a plain-language summary of what was configured.
    await expect(page.getByTestId('create-step-ready')).toHaveAttribute('aria-current', 'step');
    await expect(page.getByTestId('ready-test-call')).toBeVisible();
    await expect(page.getByTestId('ready-place-call')).toBeVisible();
    await expect(page.getByText(/is live/i).first()).toBeVisible();

    // Finishing closes the flow and lands in the agent editor.
    await page.getByTestId('create-next').click();
    await expect(page.getByTestId('create-employee-modal')).toBeHidden();
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
