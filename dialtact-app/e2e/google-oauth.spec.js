import { test, expect } from '@playwright/test';
import { googleConfig, googleStartRedirect, getSessionMeta } from './helpers/api.js';

test.describe('Google OAuth integration', () => {
  test('public config endpoint shape', async () => {
    const { ok, data } = await googleConfig();
    expect(ok).toBeTruthy();
    expect(data).toHaveProperty('enabled');
    expect(data).toHaveProperty('clientId');
    expect(data).toHaveProperty('redirectUri');
  });

  test('OAuth start redirects to Google when configured, else 503', async () => {
    const meta = await getSessionMeta();
    const { data: cfg } = await googleConfig();
    const { status, location } = await googleStartRedirect();

    if (!meta.saas_auth_enabled) {
      expect([503, 302]).toContain(status);
      return;
    }

    if (cfg.enabled) {
      expect([302, 307]).toContain(status);
      expect(location).toMatch(/accounts\.google\.com/);
      expect(location).toMatch(/client_id=/);
    } else {
      expect(status).toBe(503);
    }
  });

  test('auth modal shows Google button when entering console', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /build your agent/i }).first().click();
    await expect(page.getByRole('button', { name: /continue with google/i })).toBeVisible({
      timeout: 15000,
    });
  });
});
