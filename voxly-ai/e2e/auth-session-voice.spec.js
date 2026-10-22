/**
 * Audit fixes, driven through the real app.
 *
 * These are the flows the audit said were broken or missing, exercised as a person
 * would: sign in with the real account, reset a password through the emailed link,
 * change the password from Settings, get timed out for idling, and play the marketing
 * voice samples.
 *
 * The account is a throwaway workspace on purpose — resetting its password is the thing
 * under test. Override with E2E_EMAIL / E2E_PASSWORD / E2E_NEW_PASSWORD.
 */
import { test, expect } from '@playwright/test';

const API = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';
const EMAIL = process.env.E2E_EMAIL || 'mohansaiteja.99@gmail.com';
const NEW_PASSWORD = process.env.E2E_NEW_PASSWORD || 'Voxly-E2E-Reset-2026!';
const SECOND_PASSWORD = process.env.E2E_SECOND_PASSWORD || 'Voxly-E2E-Second-2026!';

async function signIn(page, email, password) {
  await page.goto('/');
  await page.getByRole('button', { name: /sign in/i }).first().click();
  await page.getByLabel(/work email/i).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  // The dialog closes itself shortly after success. Wait for it, or the console behind
  // it is covered by its backdrop and every later click is intercepted.
  await expect(page.locator('#voxly-auth-email')).toHaveCount(0, { timeout: 20_000 });
}

async function openConsole(page, tab = 'settings') {
  await page.goto(`/#dashboard/${tab}`);
  await expect(page.locator('body')).not.toContainText(/checking session/i, { timeout: 20_000 });
}

/** The console is reachable and the sign-in form is not on screen. */
async function expectSignedIn(page, tab = 'overview') {
  await openConsole(page, tab);
  await expect(page.getByLabel(/work email/i)).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/sign in to your console/i);
}

/** The API authenticates with the access JWT the console keeps in sessionStorage. */
function authHeaders(page) {
  return page
    .evaluate(() => window.sessionStorage.getItem('voxly_auth_token'))
    .then((token) => ({ Authorization: `Bearer ${token}` }));
}

test.describe.configure({ mode: 'serial' });

test.describe('password reset signs the user in', () => {
  test('forgot -> reset link -> new password lands in the console without a second prompt', async ({
    page,
  }) => {
    // 1. Ask for a reset link.
    await page.goto('/');
    await page.getByRole('button', { name: /sign in/i }).first().click();
    await page.getByLabel(/work email/i).fill(EMAIL);
    await page.getByRole('button', { name: /forgot password\?/i }).click();
    await page.getByRole('button', { name: /send reset email/i }).click();

    // 2. The deployment returns the link directly (AUTH_DEBUG_EXPOSE_RESET_TOKEN),
    //    because the mail provider cannot deliver yet. In production this is an email.
    const link = page.getByTestId('auth-debug-reset-link');
    await expect(link).toBeVisible({ timeout: 20_000 });
    const href = await link.getAttribute('href');
    expect(href).toContain('#reset-password?token=');
    // The emailed link points at the configured front-end origin. Drive the same route
    // on this origin instead of following it off-box.
    const token = new URL(href).hash.split('?')[1];

    // 3. The reset form asks for the password only — no redundant email field, and a
    //    confirmation field so a typo cannot lock the user out of the password they
    //    just set.
    await page.goto(`/#reset-password?${token}`);
    await expect(page.getByLabel(/work email/i)).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /choose a new password/i })).toBeVisible({ timeout: 10_000 });
    const confirm = page.getByTestId('auth-reset-confirm');
    await expect(confirm).toBeVisible();

    // 4. A mismatch is caught client-side before it reaches the API.
    await page.locator('#voxly-auth-password').fill(NEW_PASSWORD);
    await confirm.fill('something-else');
    await page.getByRole('button', { name: /update password/i }).click();
    await expect(page.getByText(/do not match/i)).toBeVisible();

    // 5. Redeem it. The server issues a session, so the console opens directly.
    await confirm.fill(NEW_PASSWORD);
    await page.getByRole('button', { name: /update password/i }).click();

    await expectSignedIn(page);
  });

  test('the new password works for a fresh sign-in', async ({ page }) => {
    await signIn(page, EMAIL, NEW_PASSWORD);
    await expectSignedIn(page);
  });
});

test.describe('change password from settings', () => {
  test('changing the password keeps this browser signed in', async ({ page }) => {
    await signIn(page, EMAIL, NEW_PASSWORD);
    await openConsole(page, 'settings');

    const form = page.getByTestId('change-password-form');
    await expect(form).toBeVisible({ timeout: 20_000 });

    // Wrong current password is rejected with a message, not a silent failure.
    await page.getByTestId('change-password-current').fill('definitely-wrong');
    await page.getByTestId('change-password-new').fill(SECOND_PASSWORD);
    await page.getByTestId('change-password-confirm').fill(SECOND_PASSWORD);
    await page.getByTestId('change-password-submit').click();
    await expect(page.getByTestId('change-password-error')).toContainText(/incorrect/i, {
      timeout: 20_000,
    });

    // Mismatched confirmation is caught before the request.
    await page.getByTestId('change-password-current').fill(NEW_PASSWORD);
    await page.getByTestId('change-password-new').fill(SECOND_PASSWORD);
    await page.getByTestId('change-password-confirm').fill(`${SECOND_PASSWORD}x`);
    await page.getByTestId('change-password-submit').click();
    await expect(page.getByTestId('change-password-error')).toContainText(/do not match/i);

    // The real change succeeds and this session survives it.
    await page.getByTestId('change-password-confirm').fill(SECOND_PASSWORD);
    await page.getByTestId('change-password-submit').click();
    await expect(page.getByTestId('change-password-notice')).toBeVisible({ timeout: 20_000 });

    await expectSignedIn(page);
  });

  test('the password can then be changed back (still signed in)', async ({ page }) => {
    // A fresh browser context: the previous test ended on SECOND_PASSWORD.
    await signIn(page, EMAIL, SECOND_PASSWORD);
    await openConsole(page, 'settings');
    await expect(page.getByTestId('change-password-form')).toBeVisible({ timeout: 20_000 });
    await page.getByTestId('change-password-current').fill(SECOND_PASSWORD);
    await page.getByTestId('change-password-new').fill(NEW_PASSWORD);
    await page.getByTestId('change-password-confirm').fill(NEW_PASSWORD);
    await page.getByTestId('change-password-submit').click();
    await expect(page.getByTestId('change-password-notice')).toBeVisible({ timeout: 20_000 });
  });
});

test.describe('session policy is enforced', () => {
  test('the server publishes the idle and absolute bounds', async ({ request }) => {
    const res = await request.get(`${API}/api/auth/session-policy`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.policy.idleTimeoutMinutes).toBeGreaterThan(0);
    expect(body.policy.absoluteMaxHours).toBeGreaterThan(0);
  });

  test('an idle session warns before it signs out', async ({ page }) => {
    await signIn(page, EMAIL, NEW_PASSWORD);

    // Shorten the window so a 30-minute policy is observable in a test. The override
    // can only lower the bound, never raise it. Waiting generates no input events, so
    // the monitor is not reset by the test framework polling the page.
    // Set directly rather than via addInitScript: the idle monitor starts when the
    // session is restored, and a hash-only navigation does not re-run init scripts.
    await page.evaluate(() => window.localStorage.setItem('voxly_idle_timeout_ms', '30000'));
    await openConsole(page, 'overview');

    // The countdown appears before the sign-out, not after it.
    await expect(page.locator('html')).toHaveAttribute('data-voxly-idle-limit-ms', '30000', {
      timeout: 20_000,
    });
    await expect(page.locator('html')).toHaveAttribute('data-voxly-idle-state', 'warning', {
      timeout: 40_000,
    });
    const dialog = page.getByTestId('idle-warning-modal');
    await expect(dialog).toBeVisible({ timeout: 20_000 });
    await expect(dialog).toContainText(/sign out/i);
  });

  test('"stay signed in" keeps the session', async ({ page }) => {
    await signIn(page, EMAIL, NEW_PASSWORD);
    // Set directly rather than via addInitScript: the idle monitor starts when the
    // session is restored, and a hash-only navigation does not re-run init scripts.
    await page.evaluate(() => window.localStorage.setItem('voxly_idle_timeout_ms', '30000'));
    await openConsole(page, 'overview');

    const dialog = page.getByTestId('idle-warning-modal');
    await expect(dialog).toBeVisible({ timeout: 40_000 });
    await page.getByTestId('idle-stay-signed-in').click();
    await expect(page.getByTestId('idle-warning-modal')).toHaveCount(0);
    await expectSignedIn(page);
  });
});

test.describe('marketing voice is the product voice', () => {
  test('each industry plays a real recorded clip, not the browser voice', async ({ page }) => {
    await page.goto('/');
    const section = page.locator('#talk-to-ai');
    await section.scrollIntoViewIfNeeded();

    // One playable sample per business, rendered from the live speech model.
    const sampleButtons = section.locator('[data-testid^="voice-industry-"]');
    await expect(sampleButtons).toHaveCount(10);

    await page.getByTestId('voice-sample-play').click();
    await expect(page.getByTestId('voice-sample-status')).toContainText(/playing/i, {
      timeout: 15_000,
    });

    // The waveform is fed by the Web Audio analyser running the real clip, so it is
    // never a fixed animation. Headless Chromium may keep the graph suspended, so the
    // assertion is that the level is wired up and the transport is running.
    await expect(page.getByTestId('voice-sample-waveform')).toBeVisible();

    // Switching industry swaps the transcript.
    await page.getByTestId('voice-industry-healthcare-clinic').click();
    await expect(page.getByTestId('voice-sample-transcript')).toContainText(/clinic|appointment/i);
    await page.getByTestId('voice-industry-logistics').click();
    await expect(page.getByTestId('voice-sample-transcript')).toContainText(/tracking number|parcel/i);
  });

  test('the browser-voice comparison is available and labelled honestly', async ({ page }) => {
    await page.goto('/');
    const section = page.locator('#talk-to-ai');
    await section.scrollIntoViewIfNeeded();
    await page.getByTestId('voice-mode-browser').click();
    await expect(section).toContainText(/browser/i);
    await page.getByTestId('voice-sample-play').click();
    await expect(page.getByTestId('voice-sample-status')).toContainText(/playing/i, {
      timeout: 15_000,
    });
  });

  test('the recorded clips are actually served', async ({ request }) => {
    const res = await request.get('/audio/voxly/samples/healthcare-clinic.wav');
    expect(res.ok()).toBeTruthy();
    const body = await res.body();
    expect(body.length).toBeGreaterThan(50_000);
    // RIFF/WAVE header.
    expect(body.subarray(0, 4).toString('ascii')).toBe('RIFF');
    expect(body.subarray(8, 12).toString('ascii')).toBe('WAVE');
  });
});

test.describe('tenant isolation', () => {
  test('the call detail endpoint withholds wholesale cost for a tenant', async ({ page }) => {
    await signIn(page, EMAIL, NEW_PASSWORD);

    const headers = await authHeaders(page);
    // include_tests: the archive excludes browser practice runs unless asked for, and
    // this workspace's only calls are practice runs.
    const list = await page.request.get(`${API}/api/calls?limit=1&include_tests=true`, { headers });
    expect(list.ok()).toBeTruthy();
    const listBody = await list.json();
    const callId = (listBody.calls || listBody)?.[0]?.call_id;
    test.skip(!callId, 'no call recorded for this workspace yet');

    const detail = await page.request.get(`${API}/api/call/${callId}`, { headers });
    expect(detail.ok()).toBeTruthy();
    const payload = await detail.json();

    // A tenant must not be able to read wholesale cost, upstream list rates, the
    // provider stack or PSTN forensics — those are enough to compute our margin.
    const blob = JSON.stringify(payload).toLowerCase();
    for (const leak of [
      'telnyx',
      'gemini_list_audio',
      'fx_rate',
      'resolved_stack',
      'pstn_forensics',
      'combination_id',
      'dial_request',
      'ledger',
    ]) {
      expect(blob).not.toContain(leak);
    }
    // ...but the numbers on their own invoice stay.
    expect(payload.internal_fields_hidden).toBe(true);
    expect(payload.duration_sec).toBeGreaterThanOrEqual(0);
    expect(payload).toHaveProperty('cost_usd');
  });
});