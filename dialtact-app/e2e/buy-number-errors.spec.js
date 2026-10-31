import { test, expect } from '@playwright/test';

// What a tenant sees when buying a number fails, for every branch the server can
// return. The API is mocked with the exact shapes server/routes/app_telephony.py
// and number_purchase_errors.py produce; no request leaves the browser.
const user = { id: 'buy-err-test', userId: 'buy-err-test', tenantId: 'buy-err-tenant', email: 'buy-err@example.invalid', hasCompletedOnboarding: true };
const numbers = [
  { e164: '+918041230002', number: '+918041230002', country: 'IN', category: 'landline', categoryLabel: 'Landline', areaLabel: 'Bengaluru (STD 080)', monthlyUsd: 6, monthlyInr: 564 },
];
const VENDOR = /vobiz|telnyx|carrier|_[a-z]+_|HTTP \d/i;

async function boot(page, { wallet = { balanceUsd: 100, balanceInr: 9000 } } = {}) {
  const errors = [];
  page.on('pageerror', (err) => errors.push(err.message));
  await page.route('**/api/**', (route) => route.fulfill({ json: {} }));
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: {
    user, tenant: { tenantId: user.tenantId, name: 'Buy Errors', status: 'active' }, role: 'customer_admin',
  } }));
  await page.route('**/api/agents', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/kyc/voice/status*', (route) => route.fulfill({ json: { required: true, configured: true, approved: true, status: 'verified' } }));
  await page.route('**/api/kyc/status', (route) => route.fulfill({ json: { required: false, configured: false, approved: false } }));
  const searches = [];
  await page.route('**/api/telephony/numbers/search?*', (route) => {
    searches.push(route.request().url());
    return route.fulfill({ json: { numbers } });
  });
  await page.route('**/api/telephony/countries', (route) => route.fulfill({ json: { countries: [{ code: 'IN', name: 'India', dial: '+91' }], default: 'IN' } }));
  await page.route('**/api/billing/catalog', (route) => route.fulfill({ json: { rates: { numberMonthlyUsd: 6, numberMonthlyInr: 564 } } }));
  await page.route('**/api/billing/wallet', (route) => route.fulfill({ json: wallet }));
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: 4070908800 })}.test`;
  await page.addInitScript(({ token, user }) => {
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_tour_completed_default', 'true');
    localStorage.setItem(`dialtact_tour_completed_${user.email}`, 'true');
  }, { token, user });
  return { errors, searches };
}

async function openAndBuy(page) {
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  const buy = page.getByTestId('buy-number-submit').first();
  await expect(buy).toHaveText('Buy number');
  await buy.click();
}

const refusal = (status, code, message) => (route) =>
  route.fulfill({ status, json: { detail: { error: { code, message, charged: false } } } });

// Every refusal the buy route can answer, with the HTTP status from
// _purchase_error_status (or the gate that raises it) and the exact tenant copy from
// TENANT_REFUSAL_MESSAGES. The KYC-gate codes open the verification step instead
// (tested below), and insufficient_balance adds the rent (tested below).
const cases = [
  { status: 503, code: 'carrier_balance_exhausted', message: "We couldn't get this number right now. Your wallet wasn't charged. Please try again later or choose another number." },
  { status: 409, code: 'carrier_price_above_retail', message: "This number isn't available at the moment. Please choose another number. You were not charged.", reloads: true },
  { status: 409, code: 'number_unavailable', message: "This number isn't available any more. Please choose another number. You were not charged.", reloads: true },
  { status: 409, code: 'number_reserved', message: 'Someone else is buying this number right now. Please choose another number. You were not charged.', reloads: true },
  { status: 503, code: 'carrier_inventory_unavailable', message: "We couldn't check this number's availability just now. Your wallet wasn't charged. Please try again in a few minutes." },
  { status: 503, code: 'carrier_not_configured', message: "Buying numbers is paused for maintenance. Your wallet wasn't charged. Please try again later." },
  { status: 502, code: 'carrier_order_failed', message: "We couldn't get this number right now. Your wallet wasn't charged. Please try again later or choose another number." },
  { status: 503, code: 'purchase_temporarily_unavailable', message: "We couldn't complete your purchase just now. Your wallet wasn't charged. Please try again in a few minutes." },
  { status: 503, code: 'voice_verification_unavailable', message: "We couldn't confirm your verification status just now. Please try again in a few minutes. You were not charged." },
  { status: 403, code: 'verification_required', message: 'Please verify your email address before buying a number. You were not charged.' },
  { status: 400, code: 'number_limit', message: 'Your workspace has reached its phone number limit. Release a number you no longer need, or contact support to raise the limit. You were not charged.' },
  { status: 400, code: 'invalid_e164', message: "That doesn't look like a valid phone number. Please choose a number from the list. You were not charged." },
  { status: 400, code: 'invalid_agent', message: 'Please choose one of your agents to answer this number, or leave it unassigned. You were not charged.' },
  { status: 404, code: 'tenant_not_found', message: "We couldn't find your workspace. Please sign in again. You were not charged." },
  { status: 400, code: 'stripe_removed', message: 'Card checkout is no longer available. Please pay from your wallet. You were not charged.' },
  { status: 429, code: 'rate_limited', message: 'Too many purchase attempts. Please wait a minute and try again. You were not charged.' },
];

for (const c of cases) {
  test(`buy refused: ${c.code} (${c.status})`, async ({ page }) => {
    const { errors, searches } = await boot(page);
    await page.route('**/api/telephony/buy', refusal(c.status, c.code, c.message));
    await openAndBuy(page);
    const box = page.getByTestId('buy-number-error');
    await expect(box).toHaveText(c.message);
    await expect(box).not.toHaveText(VENDOR);
    await expect(box).toBeInViewport();
    if (c.reloads) await expect.poll(() => searches.length).toBeGreaterThan(1);
    // Money messages stay until dismissed, in the calm warning tone, and the
    // dialog stays usable: the tenant can pick a number again.
    await page.waitForTimeout(5500);
    await expect(box).toBeVisible();
    await expect(box).toHaveClass(/bg-warning-soft/);
    if (!c.reloads) await expect(page.getByTestId('buy-number-submit').first()).toBeEnabled();
    expect(errors).toEqual([]);
  });
}

test('refusal shows next to the number tried, even far down the list', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 700 });
  const many = Array.from({ length: 12 }, (_, i) => ({ ...numbers[0], e164: `+9179654818${String(i).padStart(2, '0')}`, number: `+9179654818${String(i).padStart(2, '0')}` }));
  await boot(page);
  await page.route('**/api/telephony/numbers/search?*', (route) => route.fulfill({ json: { numbers: many } }));
  const message = cases[0].message;
  await page.route('**/api/telephony/buy', refusal(503, 'carrier_balance_exhausted', message));
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  const lastRow = page.getByTestId('buy-number-row').last();
  const buy = lastRow.getByTestId('buy-number-submit');
  await expect(buy).toHaveText('Buy number');
  await buy.scrollIntoViewIfNeeded();
  await buy.click();
  // Before the fix the alert rendered at the top of the scrolled dialog body,
  // off-screen, so the refusal looked like nothing happened.
  const box = lastRow.getByTestId('buy-number-error');
  await expect(box).toHaveText(message);
  await expect(box).toBeInViewport();
  await expect(page.getByTestId('buy-number-error')).toHaveCount(1);
  // Another number can be chosen straight away.
  await expect(page.getByTestId('buy-number-submit').first()).toBeEnabled();
});

test('internal-looking server text is replaced with plain copy', async ({ page }) => {
  await boot(page);
  await page.route('**/api/telephony/buy', refusal(500, 'boom', 'Vobiz API 500: internal_server_error'));
  await openAndBuy(page);
  await expect(page.getByTestId('buy-number-error')).toHaveText(
    "We couldn't complete your purchase just now. Your wallet wasn't charged. Please try again in a few minutes."
  );
});

test('wallet too low quotes the rent', async ({ page }) => {
  await boot(page, { wallet: { balanceUsd: 100, balanceInr: 9000 } });
  await page.route('**/api/telephony/buy', refusal(402, 'insufficient_balance',
    "Your wallet doesn't have enough credit for this number. Add credit and try again. You were not charged."));
  await openAndBuy(page);
  await expect(page.getByTestId('buy-number-error')).toContainText('₹564');
  await expect(page.getByTestId('buy-number-error')).toContainText('You were not charged.');
});

test('lost connection says the wallet was not charged', async ({ page }) => {
  await boot(page);
  await page.route('**/api/telephony/buy', (route) => route.abort('connectionreset'));
  await openAndBuy(page);
  await expect(page.getByTestId('buy-number-error')).toContainText("wasn't charged");
});

test('paid then provisioning fails: refunded message', async ({ page }) => {
  await boot(page);
  await page.route('**/api/telephony/buy', (route) => route.fulfill({ json: {
    purchaseId: 'p-1', e164: numbers[0].e164, status: 'paid', provisioning: true, payment: 'wallet',
  } }));
  await page.route('**/api/telephony/purchases/p-1', (route) => route.fulfill({ json: {
    purchaseId: 'p-1', e164: numbers[0].e164, status: 'failed', refunded: true,
    lastError: { code: 'carrier_balance_exhausted' },
    message: "We couldn't activate this number right now, so we've refunded the charge to your wallet. Please try again later or choose another number.",
  } }));
  await openAndBuy(page);
  const box = page.getByTestId('buy-number-error');
  await expect(box).toContainText("we've refunded the charge to your wallet");
  await expect(box).not.toHaveText(VENDOR);
});

test('paid then stuck: payment is safe message', async ({ page }) => {
  await boot(page);
  await page.route('**/api/telephony/buy', (route) => route.fulfill({ json: {
    purchaseId: 'p-2', e164: numbers[0].e164, status: 'paid', provisioning: true, payment: 'wallet',
  } }));
  await page.route('**/api/telephony/purchases/p-2', (route) => route.fulfill({ json: {
    purchaseId: 'p-2', e164: numbers[0].e164, status: 'needs_attention', refunded: null,
    lastError: { code: 'provider_confirmation_pending' },
    message: "Your payment is safe. Activating this number is taking longer than usual and our team has been notified. You don't need to buy it again: we'll finish the setup or refund you.",
  } }));
  await openAndBuy(page);
  await expect(page.getByTestId('buy-number-error')).toContainText('Your payment is safe.');
});

test('verification not finished opens the verification step', async ({ page }) => {
  await boot(page);
  await page.route('**/api/kyc/voice/status*', (route) => route.fulfill({ json: {
    required: true, configured: true, approved: false, status: 'pending', businessType: 'llp', legalName: 'Buy Errors LLP', identityLocked: true,
  } }));
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  await page.getByTestId('buy-number-submit').first().click();
  await expect(page.getByTestId('voice-service-kyc-card')).toBeVisible();
  await expect(page.getByTestId('voice-service-kyc-card')).toContainText('In review');
  await expect(page.getByTestId('voice-service-kyc-start')).toHaveText('Continue verification');
});

test('verification setup needing support does not offer a dead start button', async ({ page }) => {
  await boot(page);
  await page.route('**/api/kyc/voice/status*', (route) => route.fulfill({ json: {
    required: true, configured: true, approved: false, status: 'needs_review', businessType: 'llp', legalName: 'Buy Errors LLP',
  } }));
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  await page.getByTestId('buy-number-submit').first().click();
  await expect(page.getByTestId('voice-service-kyc-needs-support')).toBeVisible();
  await expect(page.getByTestId('voice-service-kyc-start')).toBeDisabled();
});
