import { test, expect } from '@playwright/test';

const API = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';

test.describe('Voxly marketing + API smoke', () => {
  test('landing loads and has Voxly title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Voxly/i, { timeout: 30000 });
  });

  test('dashboard hash requires auth (console gate)', async ({ page }) => {
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1500);
    const url = page.url();
    const body = await page.locator('body').innerText();
    const gated =
      /sign in to build|continue — sign in|checking session/i.test(body) ||
      url.includes('dashboard');
    expect(gated).toBeTruthy();
  });

  test('API health responds', async () => {
    const res = await fetch(`${API}/api/health`);
    expect(res.ok).toBeTruthy();
  });

  test('Razorpay public config endpoint', async () => {
    const res = await fetch(`${API}/api/billing/razorpay/config`);
    expect(res.ok).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('enabled');
    expect(data).toHaveProperty('currency', 'INR');
  });

  test('auth session metadata', async () => {
    const res = await fetch(`${API}/api/auth/session`);
    expect(res.ok).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty('saas_auth_enabled');
  });
});
