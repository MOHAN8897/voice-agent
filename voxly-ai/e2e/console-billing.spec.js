import { test, expect } from '@playwright/test';
import { getSessionMeta, googleConfig } from './helpers/api.js';

test.describe('Console billing (Razorpay config)', () => {
  test('razorpay public config for checkout', async () => {
    const res = await fetch(
      `${process.env.VOXLY_API_URL || 'http://127.0.0.1:8000'}/api/billing/razorpay/config`
    );
    expect(res.ok).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('enabled');
    expect(data).toHaveProperty('keyId');
    expect(data.currency).toBe('INR');
  });

  test('billing UI INR top-up (requires E2E login)', async ({ page }) => {
    const cfg = await fetch(
      `${process.env.VOXLY_API_URL || 'http://127.0.0.1:8000'}/api/billing/razorpay/config`
    ).then((r) => r.json());
    test.skip(!cfg.enabled, 'Razorpay keys not set on API');
    test.skip(!process.env.E2E_EMAIL, 'Set E2E_EMAIL/E2E_PASSWORD for billing UI test');

    await page.goto('/');
    await page.getByRole('button', { name: /build your agent/i }).first().click();
    await page.getByLabel(/work email/i).fill(process.env.E2E_EMAIL);
    await page.locator('input[type="password"]').fill(process.env.E2E_PASSWORD);
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await page.goto('/#dashboard/billing');
    await expect(page.getByText(/₹500|INR wallet|Add Funds/i).first()).toBeVisible({ timeout: 20000 });
  });
});

test.describe('Google OAuth branding', () => {
  test('config enabled with web client id', async () => {
    const meta = await getSessionMeta();
    test.skip(!meta.saas_auth_enabled, 'SAAS_AUTH_ENABLED false');
    const { data } = await googleConfig();
    expect(data.enabled).toBeTruthy();
    expect(data.clientId).toMatch(/\.apps\.googleusercontent\.com$/);
  });
});
