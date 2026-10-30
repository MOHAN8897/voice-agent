import { test, expect } from '@playwright/test';

const user = { userId: 'routing-user', fullName: 'Routing Tester', email: 'routing@example.invalid', hasCompletedOnboarding: true };
const b64 = value => Buffer.from(JSON.stringify(value)).toString('base64url');
const accessToken = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
const auth = { user, tenant: { tenantId: 'routing-tenant', name: 'Routing Workspace' }, role: 'owner', accessToken,
  sessionPolicy: { idleTimeoutMinutes: 360, absoluteMaxHours: 24, accessTokenMinutes: 15 } };

async function mockAuth(page, { handoffDelay = 0 } = {}) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data = { ok: true, items: [] };
    if (path === '/api/auth/handoff') {
      if (handoffDelay) await new Promise(resolve => setTimeout(resolve, handoffDelay));
      data = auth;
    } else if (['/api/auth/login', '/api/auth/me'].includes(path)) data = auth;
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [] };
    await route.fulfill({ json: data });
  });
  await page.addInitScript(() => {
    localStorage.setItem('dialtact_tour_completed_routing@example.invalid', 'true');
  });
}

test('email sign-in opens the requested console and keeps completed onboarding', async ({ page }) => {
  await mockAuth(page);
  await page.goto('/#dashboard/employees');
  await page.getByTestId('auth-modal').getByLabel('Work email').fill(user.email);
  await page.getByTestId('auth-modal').getByLabel('Password', { exact: true }).fill('test-only-password');
  await page.getByTestId('auth-modal').getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/#dashboard\/employees/);
  await expect(page.getByRole('button', { name: /Create AI employee/i }).first()).toBeVisible();
  await expect(page.getByTestId('onboarding-survey-modal')).toHaveCount(0);
});

test('OAuth handoff waits for authentication before opening the requested console', async ({ page }) => {
  await mockAuth(page, { handoffDelay: 200 });
  await page.addInitScript(() => {
    sessionStorage.setItem('dialtact_post_auth_tab', 'employees');
    localStorage.setItem('dialtact_last_activity_at', String(Date.now() - 60 * 60 * 1000));
  });
  await page.goto('/#auth/callback?handoff=test-single-use-handoff');
  await expect(page).toHaveURL(/#dashboard\/employees/);
  await expect(page.getByRole('button', { name: /Create AI employee/i }).first()).toBeVisible();
  await expect(page.getByTestId('auth-modal')).toHaveCount(0);
});

test('the session card and idle monitor use the 6-hour window', async ({ page }) => {
  await mockAuth(page);
  await page.goto('/#dashboard/employees');
  await page.getByTestId('auth-modal').getByLabel('Work email').fill(user.email);
  await page.getByTestId('auth-modal').getByLabel('Password', { exact: true }).fill('test-only-password');
  await page.getByTestId('auth-modal').getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'AI Employees', exact: true })).toBeVisible();
  await page.getByTestId('nav-settings').click();
  await expect(page).toHaveURL(/#dashboard\/settings/);
  await expect(page.getByTestId('session-idle-minutes')).toHaveText('6 hours');
  await expect(page.locator('html')).toHaveAttribute('data-dialtact-idle-limit-ms', '21600000');
});
