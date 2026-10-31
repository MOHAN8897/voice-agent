import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

async function checkoutFixture(page, { pending = false, holdFirstQuote = false } = {}) {
  await setupVoiceWorkspace(page);
  const state = { orders: [], verifies: 0, quotes: [], taxRate: 18, releaseQuote: null, released: false };
  function quote(amount) {
    const tax = amount * state.taxRate / 100;
    return { amount, currency: 'INR', subtotal: amount, tax, total: amount + tax,
      totalMinor: Math.round((amount + tax) * 100), creditInr: amount, cgst: tax / 2, sgst: tax / 2,
      ratePercent: state.taxRate, taxKind: 'cgst_sgst', checkoutTerms: 'Configured GST terms for this recharge.' };
  }
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path === '/api/billing/razorpay/config') return route.fulfill({ json: { enabled: true, keyId: 'fixture-only', currency: 'INR' } });
    if (path === '/api/billing/catalog') return route.fulfill({ json: { topupMinInr: 100, topupMaxInr: 10000, rates: { fxRateInr: 100 } } });
    if (path === '/api/billing/quote') {
      const body = request.postDataJSON(); state.quotes.push(body);
      const response = quote(body.amount);
      if (holdFirstQuote && state.quotes.length === 1) await new Promise(resolve => { state.releaseQuote = resolve; });
      await route.fulfill({ json: response });
      if (state.quotes.length > 1 && body.amount === 500) state.released = true;
      return;
    }
    if (path === '/api/billing/razorpay/create-order') {
      const body = request.postDataJSON(); state.orders.push(body);
      const current = quote(body.amount);
      if (body.expectedTotalMinor !== current.totalMinor) return route.fulfill({ status: 409,
        json: { detail: { error: { code: 'quote_changed', message: 'The tax or charge total changed. Review the updated quote before paying.' } } } });
      return route.fulfill({ json: { orderId: 'order-fixture', keyId: 'fixture-only', amountMinor: current.totalMinor, currency: 'INR', creditedInr: body.amount } });
    }
    if (path === '/api/billing/razorpay/verify') {
      state.verifies += 1;
      if (pending && state.verifies === 1) return route.fulfill({ status: 503, json: { detail: 'Payment verification is temporarily unavailable' } });
      return route.fulfill({ json: { ok: true, creditedInr: 500, invoiceNumber: 'INV-FIXTURE' } });
    }
    return route.fallback();
  });
  await page.evaluate(() => {
    window.__checkoutCount = 0;
    window.Razorpay = class {
      constructor(options) { this.options = options; this.handlers = {}; window.__checkout = this; }
      on(name, handler) { this.handlers[name] = handler; }
      open() { window.__checkoutCount += 1; }
    };
  });
  await page.getByTestId('sidebar-wallet-pill').click();
  await expect(page.getByTestId('add-funds-modal')).toBeVisible();
  return state;
}

async function success(page) {
  await expect.poll(() => page.evaluate(() => Boolean(window.__checkout))).toBe(true);
  await page.evaluate(() => window.__checkout.options.handler({ razorpay_order_id: 'order-fixture',
    razorpay_payment_id: 'payment-fixture', razorpay_signature: 'fixture-signature-only' }));
}

test('captured payment pending verification blocks another charge and can recover', async ({ page }) => {
  const state = await checkoutFixture(page, { pending: true });
  await expect(page.getByTestId('add-funds-submit')).toBeEnabled();
  await expect(page.getByTestId('checkout-tax-terms')).toContainText('Configured GST terms');
  await page.getByTestId('add-funds-submit').click();
  await success(page);
  await expect(page.getByTestId('add-funds-confirming')).toBeVisible();
  await expect(page.getByTestId('add-funds-submit')).toBeDisabled();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await page.getByTestId('sidebar-wallet-pill').click();
  await expect(page.getByTestId('add-funds-submit')).toBeDisabled();
  await page.getByRole('button', { name: 'Check payment status' }).click();
  await expect(page.getByText('₹500.00 added to your wallet.', { exact: true })).toBeVisible();
  expect(state.orders).toHaveLength(1);
  expect(state.orders[0].expectedTotalMinor).toBe(59000);
  expect(state.verifies).toBe(2);
});

test('failed attempt can succeed inside the same checkout without losing its success callback', async ({ page }) => {
  const state = await checkoutFixture(page);
  await expect(page.getByTestId('add-funds-submit')).toBeEnabled();
  await page.getByTestId('add-funds-submit').click();
  await expect.poll(() => page.evaluate(() => Boolean(window.__checkout))).toBe(true);
  await page.evaluate(() => window.__checkout.handlers['payment.failed']({ error: { description: 'Issuer declined this attempt' } }));
  await expect(page.getByTestId('add-funds-error')).toContainText('Issuer declined');
  await success(page);
  await expect(page.getByText('₹500.00 added to your wallet.', { exact: true })).toBeVisible();
  expect(state.orders).toHaveLength(1);
  expect(state.verifies).toBe(1);
});

test('a changed tax quote is reviewed before opening checkout', async ({ page }) => {
  const state = await checkoutFixture(page);
  await expect(page.getByTestId('add-funds-submit')).toBeEnabled();
  state.taxRate = 20;
  await page.getByTestId('add-funds-submit').click();
  await expect(page.getByTestId('add-funds-total')).toHaveText('₹600.00');
  await expect(page.getByTestId('add-funds-error')).toContainText('total changed');
  expect(await page.evaluate(() => window.__checkoutCount)).toBe(0);
});

test('a late quote for the previous amount cannot replace the current amount', async ({ page }) => {
  const state = await checkoutFixture(page, { holdFirstQuote: true });
  await expect.poll(() => Boolean(state.releaseQuote)).toBe(true);
  await page.getByTestId('add-funds-amount').fill('1000');
  await expect(page.getByTestId('add-funds-total')).toHaveText('₹1,180.00');
  state.releaseQuote();
  await expect.poll(() => state.released).toBe(true);
  await expect(page.getByTestId('add-funds-total')).toHaveText('₹1,180.00');
  await expect(page.getByTestId('add-funds-submit')).toBeEnabled();
});
