import { test, expect } from '@playwright/test';

// The buy dialog must render from every entry point. Synthetic data only; no
// request leaves the browser.
const user = { id: 'buy-ui-test', userId: 'buy-ui-test', tenantId: 'buy-test-tenant', email: 'buy-test@example.invalid', hasCompletedOnboarding: true };
const numbers = [
  { e164: '+919240900001', country: 'IN', region: '92 Series', category: 'mobile', categoryLabel: 'Mobile', areaLabel: '92 series', monthlyUsd: 4, requirements: ['Aadhaar verification of the account holder is required by the phone network for this number.'] },
  { e164: '+918041230002', country: 'IN', category: 'landline', categoryLabel: 'Landline', areaLabel: 'Bengaluru (STD 080)', city: 'Bengaluru', stdCode: '080', monthlyUsd: 4 },
  { e164: '+9118001230003', country: 'IN', category: 'toll_free', categoryLabel: 'Toll-free', monthlyUsd: 4 },
];

async function boot(page, errors) {
  page.on('pageerror', (err) => errors.push(err.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error' && /ErrorBoundary|Uncaught|is not defined|is not a function|Cannot read/i.test(msg.text())) errors.push(msg.text());
  });
  await page.route('**/api/**', (route) => route.fulfill({ json: {} }));
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: {
    user, tenant: { tenantId: user.tenantId, name: 'Buy Test', status: 'active' }, role: 'customer_admin',
  } }));
  await page.route('**/api/agents', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/kyc/voice/status*', (route) => route.fulfill({ json: { required: true, approved: true, status: 'verified' } }));
  await page.route('**/api/kyc/status', (route) => route.fulfill({ json: { required: false, configured: false, approved: false } }));
  await page.route('**/api/telephony/numbers/search?*', (route) => route.fulfill({ json: { numbers } }));
  await page.route('**/api/telephony/countries', (route) => route.fulfill({ json: { countries: [{ code: 'IN', name: 'India', dial: '+91' }], default: 'IN' } }));
  await page.route('**/api/billing/catalog', (route) => route.fulfill({ json: { rates: { numberMonthlyUsd: 4, numberMonthlyInr: 350 } } }));
  await page.route('**/api/billing/wallet', (route) => route.fulfill({ json: { balanceUsd: 100, balanceInr: 5000 } }));
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: 4070908800 })}.test`;
  await page.addInitScript(({ token, user }) => {
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_tour_completed_default', 'true');
    localStorage.setItem(`dialtact_tour_completed_${user.email}`, 'true');
  }, { token, user });
}

async function expectBuyDialog(page, errors) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Buy a phone number');
  await expect(page.getByTestId('buy-number-submit').first()).toBeVisible();
  await expect(page.getByTestId('error-boundary-fallback')).toHaveCount(0);
  expect(errors).toEqual([]);
}

test('phone numbers page button opens the buy dialog', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  await expectBuyDialog(page, errors);
});

test('top bar buy number opens the buy dialog', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  await page.goto('/#dashboard/overview');
  await page.getByTestId('topbar-buy-number').click();
  await expectBuyDialog(page, errors);
  await expect(page).toHaveURL(/#dashboard\/phone-numbers/);
});

test('command palette buy action opens the buy dialog', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  await page.goto('/#dashboard/overview');
  await page.getByRole('button', { name: 'Search workspace' }).first().click();
  await page.getByRole('dialog', { name: 'Command palette' }).getByText('Buy a phone number', { exact: true }).click();
  await expectBuyDialog(page, errors);
});

test('home buy number action opens the buy dialog', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  await page.goto('/#dashboard/overview');
  await page.locator('[data-testid="guided-buy-number"], [data-testid="rail-buy-number-btn"], [data-testid="overview-buy-number-btn"]').first().click();
  await expectBuyDialog(page, errors);
});

test('AI employee settings buy number opens the buy dialog for that employee', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  const agent = { id: 'agent-buy-1', agent_id: 'agent-buy-1', name: 'Meera', role: 'Receptionist', status: 'active' };
  await page.route('**/api/agents', (route) => route.fulfill({ json: { agents: [agent] } }));
  await page.goto('/#dashboard/employees?step=settings&agent=agent-buy-1');
  await page.getByTestId('agent-settings-buy-number').click();
  await expectBuyDialog(page, errors);
  await expect(page).toHaveURL(/#dashboard\/phone-numbers/);
  await expect(page.locator('#buy-number-agent')).toHaveValue('agent-buy-1');
});

test('buy dialog renders on a phone', async ({ page }) => {
  const errors = [];
  await page.setViewportSize({ width: 375, height: 812 });
  await boot(page, errors);
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  await expectBuyDialog(page, errors);
});

test('number types filter shows landlines with their city and STD code', async ({ page }) => {
  const errors = [];
  await boot(page, errors);
  const searches = [];
  await page.route('**/api/telephony/numbers/search?*', (route) => {
    const url = new URL(route.request().url());
    searches.push(Object.fromEntries(url.searchParams));
    return route.fulfill({ json: { numbers } });
  });
  await page.goto('/#dashboard/phone-numbers');
  await page.getByRole('button', { name: 'Buy phone number', exact: true }).click();
  await expectBuyDialog(page, errors);
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(3);

  await page.getByTestId('buy-number-type-landline').click();
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(1);
  await expect(page.getByRole('dialog')).toContainText('Bengaluru (STD 080)');
  await expect(page.getByTestId('buy-number-type-help')).toContainText('STD code');
  await expect.poll(() => searches.some((q) => q.category === 'landline')).toBe(true);

  await page.getByTestId('buy-number-type-toll_free').click();
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(1);
  await expect(page.getByRole('dialog')).toContainText('+9118001230003');

  await page.getByTestId('buy-number-type-mobile').click();
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(1);
  await expect(page.getByTestId('buy-number-requirements')).toContainText('Aadhaar');

  await page.getByTestId('buy-number-type-all').click();
  await page.getByTestId('buy-number-area').fill('Bengaluru');
  await expect(page.getByTestId('buy-number-submit')).toHaveCount(1);
  await expect.poll(() => searches.some((q) => q.area === 'Bengaluru')).toBe(true);
  await page.getByTestId('buy-number-area').fill('Chennai');
  await expect(page.getByTestId('buy-number-empty')).toBeVisible();
});
