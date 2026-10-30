import { test, expect } from '@playwright/test';

const pending = {
  required: true, configured: true, approved: false, status: 'pending', callsBlocked: true,
  identityLocked: true, businessType: 'llp', legalName: 'Example Test LLP',
  verifications: { pan: 'verified', gst: 'pending' },
};
const user = { id: 'kyc-ui-test', userId: 'kyc-ui-test', tenantId: 'kyc-test-tenant', email: 'kyc-test@example.invalid', hasCompletedOnboarding: true };

test.beforeEach(async ({ page }) => {
  // Synthetic identity and provider responses stay in this browser only.
  await page.route('**/api/**', route => route.fulfill({ json: {} }));
  await page.route('**/api/auth/me', route => route.fulfill({ json: {
    user, tenant: { tenantId: 'kyc-test-tenant', name: 'KYC Test', status: 'active' }, role: 'customer_admin',
  } }));
  await page.route('**/api/kyc/voice/status*', route => route.fulfill({ json: pending }));
  await page.route('**/api/telephony/numbers/search?*', route => route.fulfill({ json: { numbers: [{ e164: '+12025550101', country: 'US', monthlyUsd: 4 }] } }));
  await page.route('**/api/telephony/countries', route => route.fulfill({ json: { countries: [{ code: 'US', name: 'United States', dial: '+1' }], default: 'US' } }));
  await page.route('**/api/billing/catalog', route => route.fulfill({ json: { rates: { numberMonthlyUsd: 4 } } }));
  await page.route('**/api/kyc/status', route => route.fulfill({ json: { required: false, configured: false, approved: false } }));
  await page.route('**/api/billing/wallet', route => route.fulfill({ json: { balanceUsd: 100, balanceInr: 0, didMonthlyUsd: 4 } }));
  const b64 = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: 4070908800 })}.test`;
  await page.addInitScript(({ token, user }) => {
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_tour_completed_default', 'true');
    localStorage.setItem(`dialtact_tour_completed_${user.email}`, 'true');
  }, { token, user });
  await page.goto('/#dashboard/overview');
  await page.getByTestId('nav-settings').click();
  await expect(page.getByTestId('voice-service-kyc-card')).toBeVisible();
});

test('persisted identity is locked and a failed hosted session can be retried immediately', async ({ page }) => {
  await expect(page.getByTestId('voice-service-legal-name')).toHaveValue(pending.legalName);
  await expect(page.getByTestId('voice-service-legal-name')).toBeDisabled();
  await expect(page.getByTestId('voice-service-business-type')).toHaveValue('llp');
  await expect(page.getByTestId('voice-service-business-type')).toBeDisabled();
  await expect(page.getByText('GST: In review')).toBeVisible();
  let body;
  await page.route('**/api/kyc/voice/session', route => {
    body = route.request().postDataJSON();
    return route.fulfill({ status: 503, json: { detail: { error: {
      code: 'voice_kyc_session_failed', message: 'Could not start verification. Please try again.',
    } } } });
  });
  await page.getByTestId('voice-service-kyc-start').click();
  await expect(page.getByTestId('voice-service-kyc-error')).toHaveText('Could not start verification. Please try again.');
  expect(body).toMatchObject({ legal_name: pending.legalName, business_type: 'llp' });
  expect(new URL(body.return_url).origin).toBe(new URL(page.url()).origin);
  await expect(page.getByTestId('voice-service-kyc-approved')).toHaveCount(0);
  await expect(page.getByTestId('voice-service-kyc-start')).toBeEnabled();
});

test('provider-confirmed approval replaces the onboarding form', async ({ page }) => {
  await page.route('**/api/kyc/voice/status*', route => route.fulfill({ json: {
    ...pending, status: 'verified', approved: true, callsBlocked: false,
  } }));
  await page.getByTestId('voice-service-kyc-refresh').click();
  await expect(page.getByTestId('voice-service-kyc-approved')).toBeVisible();
  await expect(page.getByTestId('voice-service-kyc-card')).toHaveCount(0);
});

test('number purchase requires phone-service KYC without an additional identity gate', async ({ page }) => {
  await page.getByTestId('nav-phone-numbers').click();
  await page.getByRole('button', { name: 'Buy Phone Number', exact: true }).click();
  await expect(page.getByTestId('buy-number-submit')).toHaveText('Choose number');
  await expect(page.getByRole('dialog')).toContainText('$4.00 / month');
  await expect(page.getByTestId('voice-service-kyc-card')).toHaveCount(0);
  await page.getByTestId('buy-number-submit').click();
  await expect(page.getByTestId('voice-service-kyc-card')).toBeVisible();
  await expect(page.getByTestId('kyc-verify-card')).toHaveCount(0);
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(0);
});

test('selection survives hosted verification and returning never purchases automatically', async ({ page }) => {
  const purchases = [];
  let sessionBody;
  await page.route('**/api/telephony/buy', route => {
    purchases.push(route.request().postDataJSON());
    return route.fulfill({ json: { ok: true, phoneNumberId: 'isolated-line', e164: '+12025550101', status: 'active' } });
  });
  await page.route('https://kyc.vobiz.ai/**', route => route.fulfill({ contentType: 'text/html', body: '<p>Hosted verification test double</p>' }));
  await page.route('**/api/kyc/voice/session', route => {
    sessionBody = route.request().postDataJSON();
    return route.fulfill({ json: { ...pending, sessionUrl: 'https://kyc.vobiz.ai/verify?token=synthetic-test' } });
  });
  await page.getByTestId('nav-phone-numbers').click();
  await page.getByRole('button', { name: 'Buy Phone Number', exact: true }).click();
  await page.getByTestId('buy-number-submit').click();
  await page.getByTestId('voice-service-kyc-start').click();
  await expect(page).toHaveURL(/kyc\.vobiz\.ai/);
  expect(purchases).toHaveLength(0);
  await page.route('**/api/kyc/voice/status*', route => route.fulfill({ json: { ...pending, status: 'verified', approved: true, callsBlocked: false } }));
  await page.goto(sessionBody.return_url);
  await expect(page.getByTestId('selected-number-review')).toContainText('+12025550101');
  await expect(page.getByTestId('confirm-selected-number')).toBeEnabled();
  expect(purchases).toHaveLength(0);
  await page.getByTestId('confirm-selected-number').click();
  await expect(page.getByText('Number Successfully Provisioned!')).toBeVisible();
  expect(purchases).toHaveLength(1);
});
