import { test } from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const user = {
  id: 'u1',
  name: 'Mohan Sai Teja',
  email: 'mohan@acme.test',
  tenantId: 't1',
  tenantName: 'Acme Voice Pvt Ltd',
  role: 'owner',
  hasCompletedOnboarding: true,
};

const invoiceRows = [
  {
    invoiceId: 'inv-1',
    invoiceNumber: 'INV-2627-000001',
    createdAt: '2026-10-01T10:00:00Z',
    currency: 'INR',
    taxableInr: 10000,
    taxInr: 1800,
    gross: 11800,
    grossInr: 11800,
    taxKind: 'cgst_sgst',
    taxRatePercent: 18,
    status: 'issued',
    paymentId: 'pay_ABC123',
  },
  {
    invoiceId: 'inv-2',
    invoiceNumber: 'INV-2627-000002',
    createdAt: '2026-10-02T10:00:00Z',
    currency: 'USD',
    taxableInr: 5000,
    taxInr: 0,
    gross: 52.63,
    grossInr: 5000,
    taxKind: 'export',
    taxRatePercent: 0,
    status: 'issued',
  },
];

const invoiceDetail = {
  invoiceId: 'inv-1',
  invoiceNumber: 'INV-2627-000001',
  createdAt: '2026-10-01T10:00:00Z',
  currency: 'INR',
  taxableInr: 10000,
  taxInr: 1800,
  gross: 11800,
  grossInr: 11800,
  taxKind: 'cgst_sgst',
  taxRatePercent: 18,
  status: 'issued',
  placeOfSupply: 'Karnataka',
  placeOfSupplyCode: '29',
  paymentId: 'pay_ABC123',
  paymentMethod: 'upi',
  paidAt: '2026-10-01T10:01:00Z',
  customerGstin: '29AAPFU0939F1ZV',
  buyer: { legalName: 'Acme Voice Pvt Ltd', gstin: '29AAPFU0939F1ZV' },
  creditNotes: [
    {
      creditNoteId: 'cn-1',
      creditNoteNumber: 'CN-2627-000001',
      amountInr: 1180,
      taxInr: 180,
    },
  ],
};

const profile = {
  legalName: 'Acme Voice Pvt Ltd',
  gstin: '29AAPFU0939F1ZV',
  billingEmail: 'billing@acme.test',
  addressLine1: '14 MG Road',
  addressLine2: 'Indiranagar',
  city: 'Bengaluru',
  stateName: 'Karnataka',
  stateCode: '29',
  postalCode: '560001',
  countryCode: 'IN',
  customerType: 'business',
  complete: true,
  stateOptions: [
    { code: '29', name: 'Karnataka' },
    { code: '27', name: 'Maharashtra' },
  ],
};

const wallet = {
  currency: 'USD',
  balanceUsd: 84.96,
  balanceInr: 8124.0,
  balanceCents: 0,
  balanceInrPaise: 812400,
  remainingMinutes: 1728,
  pstnLowRateInrPerMin: 4.7,
  pstnLowRateUsdPerMin: 0.05,
  pstnMediumRateInrPerMin: 8.46,
  pstnMediumRateUsdPerMin: 0.09,
  pstnPremiumRateInrPerMin: 14.1,
  pstnPremiumRateUsdPerMin: 0.15,
  webRateInrPerMin: 4.5,
  webRateUsdPerMin: 0.048,
  myUsageUsd: 12.4,
};

const catalog = {
  topupMinInr: 100,
  topupMaxInr: 500000,
  topupMinUsd: 3,
  topupMaxUsd: 500,
  rates: { pstnUsdPerMin: 0.09, pstnInrPerMin: 8.46, fxRateInr: 95.64 },
};

/** GST-exclusive pricing: the listed amount is taxable value, GST is added. */
function quoteFor(amount, currency) {
  const subtotal = Math.round(Number(amount) * 100) / 100;
  const tax = Math.round(subtotal * 0.18 * 100) / 100;
  const total = Math.round((subtotal + tax) * 100) / 100;
  return {
    currency,
    amount: subtotal,
    subtotal,
    tax,
    total,
    creditInr: subtotal,
    taxKind: 'cgst_sgst',
    ratePercent: 18,
    rateBps: 1800,
    cgst: Math.round((tax / 2) * 100) / 100,
    sgst: Math.round((tax / 2) * 100) / 100,
    priceIncludesTax: false,
    placeOfSupply: 'Karnataka',
    placeOfSupplyCode: '29',
    minAmount: 100,
    maxAmount: 500000,
    buyer: { legalName: 'Acme Voice Pvt Ltd', gstin: '29AAPFU0939F1ZV', stateCode: '29' },
  };
}

test.use({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });

test('tenant GST invoices: breakdown, detail, PDF, profile and failed payment', async ({
  page,
  context,
}) => {
  await context.addInitScript(
    ({ session }) => {
      localStorage.setItem('voxly_auth_session', JSON.stringify(session));
      localStorage.setItem('voxly_auth_token', 'test-access-token');
      localStorage.setItem(`voxly_tour_completed_${session.email}`, 'true');
      localStorage.setItem('voxly_tour_completed_default', 'true');
      // Deterministic checkout stand-in: reports an issuer decline, never charges.
      window.Razorpay = class {
        constructor(options) {
          this.options = options;
          this.handlers = {};
        }
        on(event, fn) {
          this.handlers[event] = fn;
        }
        open() {
          setTimeout(() => {
            this.handlers['payment.failed']?.({ error: { description: 'Card declined by issuer' } });
          }, 60);
        }
      };
    },
    { session: user }
  );

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  const json = (route, body, status = 200) =>
    route.fulfill({
      status,
      headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
      body: JSON.stringify(body),
    });

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;

    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204 });
    if (p.endsWith('/api/auth/me'))
      return json(route, {
        user: { userId: 'u1', fullName: user.name, email: user.email, hasCompletedOnboarding: true },
        tenant: { tenantId: 't1', name: user.tenantName, status: 'active' },
        role: 'owner',
      });
    if (p.endsWith('/api/auth/refresh'))
      return json(route, {
        accessToken: 'test-access-token',
        user: { userId: 'u1', fullName: user.name, email: user.email, hasCompletedOnboarding: true },
        tenant: { tenantId: 't1', name: user.tenantName, status: 'active' },
        role: 'owner',
      });
    if (p.endsWith('/api/billing/wallet')) return json(route, wallet);
    if (p.endsWith('/api/billing/invoices')) return json(route, { invoices: invoiceRows });
    if (/\/api\/billing\/invoices\/[^/]+\/pdf$/.test(p))
      return route.fulfill({
        status: 200,
        headers: {
          'content-type': 'application/pdf',
          'content-disposition': 'attachment; filename="INV-2627-000001.pdf"',
        },
        body: Buffer.from('%PDF-1.4\n% mock GST invoice\n%%EOF\n'),
      });
    if (/\/api\/billing\/invoices\/[^/]+$/.test(p)) return json(route, invoiceDetail);
    if (p.endsWith('/api/billing/razorpay/config'))
      return json(route, { enabled: true, keyId: 'rzp_test_123', currency: 'INR', international: false });
    if (p.endsWith('/api/billing/catalog')) return json(route, catalog);
    if (p.endsWith('/api/billing/quote')) {
      const body = JSON.parse(req.postData() || '{}');
      return json(route, quoteFor(body.amount ?? 500, body.currency || 'INR'));
    }
    if (p.endsWith('/api/billing/razorpay/create-order')) {
      const body = JSON.parse(req.postData() || '{}');
      const q = quoteFor(body.amount ?? 500, body.currency || 'INR');
      return json(route, {
        orderId: 'order_test_1',
        keyId: 'rzp_test_123',
        currency: 'INR',
        amount: q.total,
        amountMinor: Math.round(q.total * 100),
        subtotal: q.subtotal,
        subtotalMinor: Math.round(q.subtotal * 100),
        tax: q.tax,
        taxMinor: Math.round(q.tax * 100),
        taxRatePercent: 18,
        taxKind: 'cgst_sgst',
        cgst: q.cgst,
        sgst: q.sgst,
      });
    }
    if (p.endsWith('/api/billing/razorpay/verify')) return json(route, { ok: true });
    if (p.endsWith('/api/billing/profile')) {
      if (req.method() === 'PUT') {
        const body = JSON.parse(req.postData() || '{}');
        return json(route, { ...profile, ...body, complete: true });
      }
      return json(route, profile);
    }
    if (p.endsWith('/api/billing/transactions'))
      return json(route, {
        transactions: [
          {
            id: 'tx-1',
            kind: 'topup',
            amountUsd: 100,
            amountInr: 9500,
            createdAt: '2026-10-01T10:01:00Z',
            description: 'Wallet top-up',
          },
        ],
      });
    if (p.endsWith('/api/billing/last-session')) return json(route, { has_call: false });
    if (p.endsWith('/api/support/config')) return json(route, { config: {} });
    return json(route, {});
  });

  await page.goto('/#dashboard/billing', { waitUntil: 'domcontentloaded' });
  await page.getByText('INV-2627-000001', { exact: true }).waitFor({ timeout: 45000 });

  const firstRow = page.locator('tr', { hasText: 'INV-2627-000001' }).first();
  const rowText = await firstRow.innerText();
  assert.match(rowText, /₹10,000\.00/, 'taxable value should render in INR');
  assert.match(rowText, /₹1,800\.00/, 'GST amount should render in INR');
  assert.match(rowText, /CGST \+ SGST @ 18%/, 'CGST+SGST split should be labelled');
  assert.match(rowText, /₹11,800\.00/, 'gross paid should include GST');

  const secondRow = page.locator('tr', { hasText: 'INV-2627-000002' }).first();
  const secondText = await secondRow.innerText();
  assert.match(secondText, /Zero-rated export/, 'USD charge should show zero-rated export');

  await page.click('[data-testid="billing-invoice-detail-INV-2627-000001"]');
  await page.getByText('Place of supply', { exact: true }).waitFor({ timeout: 10000 });
  const detailText = await page.locator('tr', { hasText: 'Place of supply' }).innerText();
  assert.match(detailText, /Karnataka \(29\)/, 'place of supply should be shown');
  assert.match(detailText, /pay_ABC123/, 'payment reference should be shown');
  assert.match(detailText, /Acme Voice Pvt Ltd/, 'buyer legal name should be shown');
  assert.match(detailText, /GSTIN 29AAPFU0939F1ZV/, 'buyer GSTIN should be shown');
  assert.match(detailText, /CN-2627-000001/, 'credit note should be listed');
  assert.match(detailText, /₹180\.00/, 'credit note GST should be listed');

  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    page.click('[data-testid="billing-invoice-download-INV-2627-000001"]'),
  ]);
  assert.equal(download.suggestedFilename(), 'INV-2627-000001.pdf');
  const saved = path.join(os.tmpdir(), 'gst-invoice-verify.pdf');
  await download.saveAs(saved);
  assert.equal(fs.readFileSync(saved).subarray(0, 8).toString(), '%PDF-1.4');
  fs.unlinkSync(saved);

  await page.click('[data-testid="billing-profile-edit"]');
  await page.getByTestId('billing-profile-form').waitFor({ timeout: 10000 });
  assert.equal(await page.getByTestId('billing-profile-gstin').inputValue(), '29AAPFU0939F1ZV');
  await page
    .locator('form[data-testid="billing-profile-form"]')
    .getByRole('button', { name: /save/i })
    .click();
  await page.getByText('Invoice profile saved. New invoices will use it.').waitFor({ timeout: 10000 });

  await page.click('[data-testid="billing-add-funds"]');
  await page.getByTestId('add-funds-modal').waitFor({ timeout: 10000 });
  await page.waitForFunction(
    () => /₹/.test(document.querySelector('[data-testid="add-funds-total"]')?.textContent || ''),
    null,
    { timeout: 10000 }
  );
  const breakdown = await page.getByTestId('add-funds-breakdown').innerText();
  assert.match(breakdown, /Wallet credit \(taxable value\)/, 'credit line should be present');
  assert.match(breakdown, /CGST \+ SGST @ 18%/, 'GST line should be present');
  assert.match(breakdown, /₹500\.00/, 'taxable value should be quoted');
  assert.match(breakdown, /₹90\.00/, 'GST at 18% should be quoted');
  assert.match(await page.getByTestId('add-funds-total').innerText(), /₹590\.00/);

  await page.getByTestId('add-funds-submit').click();
  await page.getByTestId('add-funds-error').waitFor({ timeout: 15000 });
  const paymentError = await page.getByTestId('add-funds-error').innerText();
  assert.match(paymentError, /Card declined by issuer/);
  assert.match(paymentError, /No wallet credit was added/);

  const relevantConsoleErrors = consoleErrors.filter(
    (line) => !/Failed to load resource|net::ERR|ECONNREFUSED|favicon/i.test(line)
  );
  assert.deepEqual(relevantConsoleErrors, []);
});
