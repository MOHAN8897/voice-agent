import { test, expect } from '@playwright/test';

/**
 * Deleted workspace → sign in again → restore screen → restore → console.
 *
 * The API is a stateful in-page mock that answers exactly like the FastAPI routes:
 * every ordinary request for a workspace pending deletion is 403 tenant_quarantined,
 * and only /api/tenant/restore-status, /api/tenant/restore and export answer.
 * Before the fix, the first such 403 dropped the session and bounced the owner back
 * to the sign-in page, so the restore action was never reachable.
 */

const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
const accessToken = `${b64({ alg: 'none' })}.${b64({ sub: 'restore-owner', exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
const purgeAt = new Date(Date.now() + 13 * 86400000).toISOString();

function mockBackend(page, { role = 'customer_admin', reauthRequired = false } = {}) {
  const state = { status: 'quarantined', restoreCalls: 0, otherRequestsWhileQuarantined: 0, refusedPaths: [], restoreBody: null };
  const user = {
    userId: 'restore-owner',
    fullName: 'Restore Owner',
    email: 'restore.owner@example.invalid',
    hasCompletedOnboarding: true,
  };
  const session = () => ({
    user,
    tenant: {
      tenantId: 'restore-tenant',
      name: 'Acme Restore',
      status: state.status,
      scheduledPurgeAt: state.status === 'quarantined' ? purgeAt : null,
    },
    role,
    accessToken,
    sessionPolicy: { idleTimeoutMinutes: 360, absoluteMaxHours: 24, accessTokenMinutes: 15 },
  });

  page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (['/api/auth/login', '/api/auth/me', '/api/auth/refresh'].includes(path)) {
      return route.fulfill({ json: session() });
    }
    if (path === '/api/auth/session') return route.fulfill({ json: { saas_auth_enabled: true } });
    if (path === '/api/auth/logout') return route.fulfill({ json: { ok: true } });
    if (path === '/api/tenant/restore-status') {
      if (state.status === 'active') return route.fulfill({ json: { status: 'active', tenantName: 'Acme Restore' } });
      const owner = role === 'customer_admin';
      return route.fulfill({
        json: {
          status: 'quarantined',
          tenantName: 'Acme Restore',
          scheduledPurgeAt: purgeAt,
          daysRemaining: 13,
          inGracePeriod: true,
          canRestore: owner,
          restoreBlockedReason: owner ? null : 'not_owner',
          reauthRequired,
          hasPassword: true,
          deletedByYou: owner,
          restorePreview: {
            agents: 3,
            phoneNumbers: 2,
            campaignsPaused: 1,
            integrations: 0,
            walletBalanceUsd: 0,
            walletBalanceInr: 1500,
          },
        },
      });
    }
    if (path === '/api/tenant/restore') {
      state.restoreCalls += 1;
      state.restoreBody = req.postDataJSON?.() ?? null;
      if (reauthRequired && !state.restoreBody?.current_password) {
        return route.fulfill({ status: 403, json: { detail: { error: 'reauth_required', message: 'Confirm it is you.' } } });
      }
      state.status = 'active';
      return route.fulfill({ json: { status: 'active', alreadyActive: false, restored: { phoneNumbers: 2 } } });
    }
    // Only signed-in requests hit the quarantine guard; public config endpoints do not.
    const authed = Boolean(req.headers()['authorization']);
    if (state.status === 'quarantined' && authed) {
      state.otherRequestsWhileQuarantined += 1;
      state.refusedPaths.push(path);
      return route.fulfill({
        status: 403,
        json: { detail: { error: 'tenant_quarantined', message: 'Restore it to continue.', scheduledPurgeAt: purgeAt } },
      });
    }
    if (path === '/api/agents') return route.fulfill({ json: { agents: [] } });
    return route.fulfill({ json: { ok: true, items: [] } });
  });
  page.addInitScript(() => {
    localStorage.setItem('dialtact_tour_completed_restore.owner@example.invalid', 'true');
  });
  return state;
}

async function signIn(page) {
  await page.goto('/login?notice=workspace_quarantined');
  const modal = page.getByTestId('auth-modal');
  await expect(modal).toContainText('scheduled for deletion');
  await modal.getByLabel('Work email').fill('restore.owner@example.invalid');
  await modal.getByLabel('Password', { exact: true }).fill('test-only-password');
  await modal.getByRole('button', { name: 'Sign in', exact: true }).click();
}

test('owner signs in again, sees the restore screen, restores, and lands in the console', async ({ page }) => {
  const state = mockBackend(page);
  await signIn(page);

  const screen = page.getByTestId('workspace-restore-screen');
  await expect(screen).toBeVisible();
  await expect(screen.getByRole('heading', { name: 'Acme Restore' })).toBeVisible();
  await expect(page.getByTestId('restore-preview')).toContainText('3 AI employees');
  await expect(page.getByTestId('restore-preview')).toContainText('2 phone numbers');
  await expect(screen).toContainText('1 campaign stays paused');
  // Still signed in on the restore screen; nothing bounced us to the sign-in page.
  await expect(page.getByTestId('auth-modal')).toHaveCount(0);
  expect(state.refusedPaths).toEqual([]);

  await page.getByTestId('restore-workspace').click();
  await expect(screen).toHaveCount(0);
  expect(state.restoreCalls).toBe(1);
  await expect(page).toHaveURL(/#dashboard\/overview/);
  await expect(page.getByTestId('auth-modal')).toHaveCount(0);
});

test('a stale session asks for the password before restoring', async ({ page }) => {
  const state = mockBackend(page, { reauthRequired: true });
  await signIn(page);
  await expect(page.getByTestId('workspace-restore-screen')).toBeVisible();
  await expect(page.getByTestId('restore-workspace')).toBeDisabled();
  await page.getByTestId('restore-password').fill('test-only-password');
  await page.getByTestId('restore-workspace').click();
  await expect(page.getByTestId('workspace-restore-screen')).toHaveCount(0);
  expect(state.restoreBody).toEqual({ current_password: 'test-only-password' });
});

test('a member sees why they cannot get in and no restore button', async ({ page }) => {
  mockBackend(page, { role: 'customer_viewer' });
  await signIn(page);
  await expect(page.getByTestId('restore-blocked')).toContainText('Only the workspace owner can restore it');
  await expect(page.getByTestId('restore-workspace')).toHaveCount(0);
});

test('phone width: the restore screen fits without horizontal scroll', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  mockBackend(page);
  await signIn(page);
  await expect(page.getByTestId('workspace-restore-screen')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
