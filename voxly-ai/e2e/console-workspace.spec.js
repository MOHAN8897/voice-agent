import { test, expect } from '@playwright/test';
import { getSessionMeta, login } from './helpers/api.js';

const E2E_EMAIL = process.env.E2E_EMAIL;
const E2E_PASSWORD = process.env.E2E_PASSWORD;

test.describe('Console workspace sync', () => {
  test.beforeAll(async () => {
    const meta = await getSessionMeta();
    if (!meta.saas_auth_enabled) {
      test.skip(true, 'SAAS_AUTH_ENABLED is false on API');
    }
  });

  test('signed-in dashboard shows sync banner only on API errors', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await page.goto('/');
    await page.getByRole('button', { name: /sign in/i }).first().click();
    await page.getByLabel(/work email/i).fill(E2E_EMAIL);
    await page.locator('input[type="password"]').fill(E2E_PASSWORD);
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await page.waitForTimeout(1500);
    await page.goto('/#dashboard/overview');
    await expect(page.getByRole('heading', { name: /good afternoon/i })).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText(/voice agent/i).first()).toBeVisible();
  });

  test('wallet config endpoint reachable with auth', async () => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');
    const auth = await login(E2E_EMAIL, E2E_PASSWORD);
    expect(auth.ok).toBeTruthy();
    const base = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';
    const res = await fetch(`${base}/api/billing/wallet`, {
      headers: { Authorization: `Bearer ${auth.data.accessToken}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('balanceUsd');
  });
});
