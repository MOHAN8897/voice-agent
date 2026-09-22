import { test, expect } from '@playwright/test';
import {
  createAgent,
  getMe,
  getSessionMeta,
  listAgents,
  login,
  signup,
} from './helpers/api.js';

const E2E_EMAIL = process.env.E2E_EMAIL;
const E2E_PASSWORD = process.env.E2E_PASSWORD;

test.describe('SaaS subscriber API flow', () => {
  test.beforeAll(async () => {
    const meta = await getSessionMeta();
    if (!meta.saas_auth_enabled) {
      test.skip(true, 'SAAS_AUTH_ENABLED is false on API');
    }
  });

  test('protected agents requires bearer token', async () => {
    const res = await fetch(
      `${process.env.VOXLY_API_URL || 'http://127.0.0.1:8000'}/api/agents`
    );
    expect(res.status).toBe(401);
  });

  test('email login + agent CRUD (verified user)', async () => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD to a verified user');

    const auth = await login(E2E_EMAIL, E2E_PASSWORD);
    expect(auth.ok).toBeTruthy();
    const token = auth.data.accessToken;
    expect(token).toBeTruthy();

    const me = await getMe(token);
    expect(me.ok).toBeTruthy();
    expect(me.data.user?.email).toBeTruthy();

    const agentName = `E2E Agent ${Date.now()}`;
    const created = await createAgent(token, agentName);
    expect(created.ok).toBeTruthy();
    expect(created.data.agent?.name || created.data.name).toBe(agentName);

    const listed = await listAgents(token);
    expect(listed.ok).toBeTruthy();
    const agents = listed.data.agents || listed.data;
    expect(agents.some((a) => a.name === agentName)).toBeTruthy();
  });

  test('signup returns verification requirement (no immediate tokens)', async () => {
    const meta = await getSessionMeta();
    test.skip(!meta.saas_auth_enabled, 'SAAS_AUTH_ENABLED is false on API');

    const email = `e2e.${Date.now()}@example.com`;
    const res = await signup(email, 'TestPass123!', 'E2E', 'E2E Co');
    expect(res.status).toBe(200);
    expect(res.data.requiresEmailVerification).toBe(true);
    expect(res.data.accessToken).toBeFalsy();
  });

  test('console UI login opens dashboard with verified user', async ({ page }) => {
    test.skip(!E2E_EMAIL || !E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD');

    await page.goto('/');
    await page.getByRole('button', { name: /sign in/i }).first().click();
    await page.getByLabel(/work email/i).fill(E2E_EMAIL);
    await page.locator('input[type="password"]').fill(E2E_PASSWORD);
    await page.getByRole('button', { name: /^sign in$/i }).click();
    await page.waitForTimeout(2000);
    await page.goto('/#dashboard/overview');
    await expect(page.locator('body')).not.toContainText(/checking session/i, { timeout: 15000 });
    await expect(page.locator('body')).toContainText(/overview|employees|agent/i);
  });
});
