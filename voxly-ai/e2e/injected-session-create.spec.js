import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionPath = path.resolve(__dirname, '../../data/e2e_session.json');

test('create employee with injected dev-tester session', async ({ page }) => {
  test.skip(!fs.existsSync(sessionPath), 'Run scripts to create data/e2e_session.json first');

  const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
  const u = sess.user;
  const sessionUser = {
    id: u.userId,
    name: u.fullName || u.email,
    email: u.email,
    tenantId: sess.tenant?.tenantId,
  };

  await page.addInitScript(
    ({ token, sessionUser }) => {
      sessionStorage.setItem('voxly_auth_token', token);
      localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
    },
    { token: sess.token, sessionUser }
  );

  await page.goto('/#dashboard/employees');
  await page.waitForFunction(() => !document.body.innerText.includes('Checking session'), {
    timeout: 20000,
  });
  await expect(page.getByRole('heading', { name: /ai employees/i }).first()).toBeVisible({
    timeout: 30000,
  });

  await page.getByRole('button', { name: /create ai employee/i }).click();
  await expect(page.getByTestId('create-employee-modal')).toBeVisible();

  const brief =
    'Playwright E2E dummy agent for a spa in Hyderabad. Book appointments and collect caller name.';
  await page.getByTestId('employee-brief-input').fill(brief);
  await page.getByTestId('create-next').click();

  // Step 2 reviews the compiled script before anything is saved or dialled.
  await expect(page.getByTestId('create-step-script')).toHaveAttribute('aria-current', 'step', {
    timeout: 120000,
  });
  await expect(page.getByTestId('script-preview')).not.toBeEmpty({ timeout: 30000 });

  // Walk the remaining steps to finish the flow.
  await page.getByTestId('create-next').click(); // -> configure
  await expect(page.getByTestId('create-step-configure')).toHaveAttribute('aria-current', 'step');
  await page.getByTestId('create-next').click(); // -> ready
  await expect(page.getByTestId('create-step-ready')).toHaveAttribute('aria-current', 'step');

  await page.getByTestId('create-next').click(); // done
  await expect(page.getByTestId('create-employee-modal')).toBeHidden({ timeout: 60000 });
  await expect(page.getByText(/script|calling|greeting|opening/i).first()).toBeVisible({
    timeout: 30000,
  });
});
