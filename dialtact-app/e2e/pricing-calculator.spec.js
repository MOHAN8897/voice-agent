import { expect, test } from '@playwright/test';

const inr = (text) => Number(String(text).replace(/[^\d.]/g, ''));
const money = (value) =>
  `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

async function setRange(page, selector, value) {
  await page.locator(selector).evaluate((el, next) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, String(next));
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

async function expectMoneyClose(locator, expected) {
  const shown = inr(await locator.innerText());
  expect(Math.abs(shown - expected)).toBeLessThan(0.02);
}

function fixtureCatalog(overrides = {}) {
  return {
    currency: 'USD',
    plans: [],
    numberSkus: [
      { country: 'IN', currency: 'USD', monthlyCents: 40000, monthlyUsd: 4, monthlyInr: 564 },
    ],
    rates: { fxRateInr: 94 },
    tax: { enabled: true, ratePercent: 18, priceIncludesTax: false, countryCode: 'IN' },
    pricingVersion: 1,
    merchandisingVersion: 2,
    featuredStyle: 'graphite',
    calculator: {
      allowMinuteInput: true,
      compareTiers: true,
      shareableEstimate: true,
      showGstToggle: true,
    },
    tiers: [
      {
        id: 'alpha',
        label: 'Alpha tier',
        featured: false,
        visible: true,
        tags: [{ label: 'Alpha tag', tone: 'accent' }],
        pstn: { usdPerMin: 0.05, inrPerMin: 5 },
      },
      {
        id: 'beta',
        label: 'Beta tier',
        featured: true,
        visible: true,
        tags: [],
        pstn: { usdPerMin: 0.07, inrPerMin: 7 },
      },
    ],
    ...overrides,
  };
}

test('the calculator is backend-driven and offers volume, comparison, GST and shared links', async ({
  page,
  request,
}) => {
  const catalog = await (await request.get('/api/billing/catalog')).json();
  const priced = catalog.tiers.filter(
    (tier) => tier?.visible !== false && Number.isFinite(tier?.pstn?.inrPerMin)
  );
  test.skip(priced.length === 0, 'No published phone rate to estimate');

  const tax = catalog.tax || {};
  const gstRate = tax.enabled === true && Number(tax.ratePercent) > 0 ? Number(tax.ratePercent) : 0;
  const flags = catalog.calculator || {};
  const inclusivePrices = tax.priceIncludesTax === true;
  const exFactor = gstRate > 0 && inclusivePrices ? 1 / (1 + gstRate / 100) : 1;
  const taxMultiplier = 1 + gstRate / 100;

  await page.goto('/');
  const calculator = page.getByTestId('usage-calculator');
  await expect(calculator).toBeVisible();

  const first = priced[0];
  const optionLabels = await page.locator('#usage-tier option').allTextContents();
  expect(optionLabels).toEqual(priced.map((tier) => tier.label));

  await page.locator('#usage-tier').selectOption(first.id);
  await expect(page.getByTestId('usage-tier-rate')).toContainText(
    `${money(first.pstn.inrPerMin)} per phone minute`
  );

  const calculatorTags = first.tags || [];
  const tagItems = calculator.locator('.usage-tier-tags li');
  await expect(tagItems).toHaveCount(calculatorTags.length);
  for (let index = 0; index < calculatorTags.length; index += 1) {
    await expect(tagItems.nth(index)).toHaveText(calculatorTags[index].label);
  }

  await page.getByRole('button', { name: '500', exact: true }).click();
  await setRange(page, '#usage-minutes', 1.5);
  await expect(page.getByTestId('usage-talk-time')).toContainText(
    '500 calls × 1.5 min = 750 min of talk time'
  );

  const exTotal = 750 * first.pstn.inrPerMin * exFactor;
  const inclTotal = exTotal * taxMultiplier;
  const gstToggle = page.getByTestId('usage-gst-ex');
  const hasGstToggle =
    flags.showGstToggle !== false && gstRate > 0 && (await gstToggle.count()) > 0;

  const breakdown = page.locator('.usage-breakdown dd');
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), exTotal);
  await expect(page.getByTestId('usage-estimate-formula')).toContainText(`750 min × ${money(first.pstn.inrPerMin * exFactor)}/min`);

  if (hasGstToggle) {
    await expect(gstToggle).toContainText(money(exTotal));
    await expect(page.getByTestId('usage-gst-incl')).toContainText(money(inclTotal));
    await expect(breakdown).toHaveCount(5);
    await expectMoneyClose(breakdown.nth(2), exTotal);
    await expectMoneyClose(breakdown.nth(3), inclTotal - exTotal);
    await expectMoneyClose(breakdown.nth(4), exTotal / 500);

    await page.getByTestId('usage-gst-incl').click();
    await expectMoneyClose(page.getByTestId('usage-estimate-total'), inclTotal);
    await expect(page.getByTestId('usage-estimate-formula')).toContainText(
      `incl. ${gstRate}% GST`
    );
    await expectMoneyClose(breakdown.nth(4), inclTotal / 500);
    await page.getByTestId('usage-gst-ex').click();
    await expectMoneyClose(page.getByTestId('usage-estimate-total'), exTotal);
  } else {
    await expect(breakdown).toHaveCount(3);
    await expectMoneyClose(breakdown.nth(2), exTotal / 500);
  }

  const compare = page.getByTestId('usage-compare');
  if (flags.compareTiers !== false && priced.length > 1) {
    await expect(compare).toBeVisible();
    const cards = compare.locator('.usage-compare-card');
    await expect(cards).toHaveCount(priced.length);
    const compareRates = await compare.locator('.usage-compare-rate').allTextContents();
    expect(compareRates).toEqual(priced.map((tier) => `${money(tier.pstn.inrPerMin)}/min`));

    const second = priced[1];
    // The dropdown is the only tier selector; comparison cards stay informational.
    await expect(compare.getByRole('button')).toHaveCount(0);
    await page.locator(`.usage-compare-card[data-tier="${second.id}"]`).click();
    await expect(page.locator('#usage-tier')).toHaveValue(first.id);
    await page.locator('#usage-tier').selectOption(second.id);
    await expectMoneyClose(
      page.getByTestId('usage-estimate-total'),
      750 * second.pstn.inrPerMin * exFactor
    );
    await page.locator('#usage-tier').selectOption(first.id);
    await expectMoneyClose(page.getByTestId('usage-estimate-total'), exTotal);
  } else {
    await expect(compare).toHaveCount(0);
  }

  if (flags.allowMinuteInput !== false) {
    await page.getByTestId('usage-mode-minutes').click();
    await expect(page.locator('#usage-monthly-minutes')).toBeVisible();
    await setRange(page, '#usage-monthly-minutes', 800);
    await setRange(page, '#usage-minutes', 2);
    await expect(page.getByTestId('usage-talk-time')).toContainText('about 400 calls');
    await expectMoneyClose(page.getByTestId('usage-estimate-total'), 800 * first.pstn.inrPerMin * exFactor);
  } else {
    await expect(page.locator('#usage-monthly-minutes')).toHaveCount(0);
  }

  if (flags.shareableEstimate !== false) {
    await expect(page).toHaveURL(/[?&]tier=/);
    const url = new URL(page.url());
    expect(url.searchParams.get('tier')).toBe(first.id);
    expect(url.searchParams.get('mode')).toBe(flags.allowMinuteInput === false ? 'calls' : 'minutes');
    if (flags.allowMinuteInput !== false) {
      expect(url.searchParams.get('mins')).toBe('800');
      expect(url.searchParams.get('len')).toBe('2');
    }

    const totalBefore = inr(await page.getByTestId('usage-estimate-total').innerText());
    await page.reload();
    await expect(page.locator('#usage-tier')).toHaveValue(first.id);
    if (flags.allowMinuteInput !== false) {
      await expect(page.getByTestId('usage-mode-minutes')).toHaveAttribute('aria-pressed', 'true');
    }
    await expectMoneyClose(page.getByTestId('usage-estimate-total'), totalBefore);

    await page
      .getByTestId('usage-share')
      .getByRole('button', { name: /copy estimate link/i })
      .click();
    await expect(page.getByTestId('usage-share')).toContainText(/copied|copy failed/i);
  } else {
    await expect(page.getByTestId('usage-share')).toHaveCount(0);
  }

  await expect(calculator).not.toContainText(/browser agent|web agent|mixed/i);
  await expect(calculator).not.toContainText('$');
  const numberInr = catalog.numberSkus?.[0]?.monthlyInr;
  if (Number.isFinite(numberInr)) {
    await expect(calculator).not.toContainText(numberInr.toLocaleString('en-IN'));
  }

  for (const tier of priced) {
    const card = page.locator(`#pricing .landing-price-card[data-tier="${tier.id}"]`);
    await expect(card).toBeVisible();
    const cardTags = card.locator('.landing-price-tags li');
    const expectedTags = tier.tags || [];
    await expect(cardTags).toHaveCount(expectedTags.length);
    for (let index = 0; index < expectedTags.length; index += 1) {
      await expect(cardTags.nth(index)).toHaveText(expectedTags[index].label);
    }
  }
  await expect(page.locator('#pricing')).not.toContainText(/browser agent|web agent/i);
});

test('GST view follows the published tax config in both directions', async ({ page }) => {
  await page.route('**/api/billing/catalog', (route) =>
    route.fulfill({ json: fixtureCatalog() })
  );
  await page.goto('/');

  const calculator = page.getByTestId('usage-calculator');
  await expect(calculator).toBeVisible();
  await page.getByRole('button', { name: '500', exact: true }).click();
  await setRange(page, '#usage-minutes', 2);

  const rows = page.locator('.usage-breakdown dd');
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 5000);
  await expect(page.getByTestId('usage-gst-ex')).toContainText('₹5,000.00');
  await expect(page.getByTestId('usage-gst-incl')).toContainText('₹5,900.00');
  await expect(rows).toHaveCount(5);
  await expectMoneyClose(rows.nth(2), 5000);
  await expectMoneyClose(rows.nth(3), 900);
  await expectMoneyClose(rows.nth(4), 10);

  await page.getByTestId('usage-gst-incl').click();
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 5900);
  await expect(page.getByTestId('usage-estimate-formula')).toContainText('incl. 18% GST');
  await expectMoneyClose(rows.nth(4), 11.8);
  await expect(page).toHaveURL(/[?&]gst=incl/);

  const beta = page.locator('.usage-compare-card[data-tier="beta"]');
  await expect(beta).toContainText('₹8,260.00');
  await expect(page.getByTestId('usage-compare').getByRole('button')).toHaveCount(0);
  await page.locator('#usage-tier').selectOption('beta');
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 8260);

  await page.getByTestId('usage-gst-ex').click();
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 7000);
  await expectMoneyClose(rows.nth(2), 7000);
  await expectMoneyClose(rows.nth(3), 1260);
});

test('inclusive shelf prices open in the incl-GST view', async ({ page }) => {
  await page.route('**/api/billing/catalog', (route) =>
    route.fulfill({
      json: fixtureCatalog({
        tax: { enabled: true, ratePercent: 18, priceIncludesTax: true, countryCode: 'IN' },
      }),
    })
  );
  await page.goto('/');

  const calculator = page.getByTestId('usage-calculator');
  await expect(calculator).toBeVisible();
  await page.getByRole('button', { name: '500', exact: true }).click();
  await setRange(page, '#usage-minutes', 2);

  // Alpha publishes ₹5.00 per minute including GST, so the default total is the
  // shelf amount the pricing card shows, not a cheaper ex-GST figure.
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 5000);
  await expect(page.getByTestId('usage-estimate-formula')).toContainText('incl. 18% GST');
  await expect(page.getByTestId('usage-gst-ex')).toContainText('₹4,237.29');
  await expect(page.getByTestId('usage-gst-incl')).toContainText('₹5,000.00');
  await expect(page).toHaveURL(/[?&]gst=incl/);

  await page.getByTestId('usage-gst-ex').click();
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 4237.29);
  await expect(page.locator('.usage-breakdown dd').nth(2)).toContainText('₹4,237.29');
  await expect(page.locator('.usage-breakdown dd').nth(3)).toContainText('₹762.71');
  await expect(page).toHaveURL(/[?&]gst=ex/);
});

test('shared estimates contain only estimate fields on the public pricing page', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true,
      value: { writeText: async (value) => { window.auditSharedEstimate = value; } } });
  });
  await page.route('**/api/billing/catalog', (route) => route.fulfill({ json: fixtureCatalog() }));
  await page.goto('/pricing?token=synthetic-only&email=fixture%40example.invalid#private-fragment');
  await page.getByTestId('usage-share').getByRole('button', { name: /copy estimate link/i }).click();
  await expect(page.getByTestId('usage-share')).toContainText('copied');
  const shared = new URL(await page.evaluate(() => window.auditSharedEstimate));
  expect(shared.pathname).toBe('/pricing');
  expect(shared.hash).toBe('');
  expect([...shared.searchParams.keys()].every((key) => ['tier', 'mode', 'calls', 'len', 'mins', 'gst'].includes(key))).toBe(true);
});

test('hiding the GST toggle preserves inclusive shelf-price meaning', async ({ page }) => {
  await page.route('**/api/billing/catalog', (route) => route.fulfill({ json: fixtureCatalog({
    tax: { enabled: true, ratePercent: 18, priceIncludesTax: true, countryCode: 'IN' },
    calculator: { allowMinuteInput: true, compareTiers: true, shareableEstimate: true, showGstToggle: false },
  }) }));
  await page.goto('/pricing');
  await page.locator('#usage-tier').selectOption('alpha');
  await page.getByRole('button', { name: '500', exact: true }).click();
  await setRange(page, '#usage-minutes', 2);
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 5000);
  await expect(page.getByTestId('usage-gst-ex')).toHaveCount(0);
  await expect(page.getByTestId('usage-estimate-formula')).toContainText('incl. 18% GST');
});

test('operator switches hide calculator features without touching the estimate', async ({
  page,
}) => {
  await page.route('**/api/billing/catalog', (route) =>
    route.fulfill({
      json: fixtureCatalog({
        calculator: {
          allowMinuteInput: false,
          compareTiers: false,
          shareableEstimate: false,
          showGstToggle: false,
        },
      }),
    })
  );
  await page.goto('/');

  const calculator = page.getByTestId('usage-calculator');
  await expect(calculator).toBeVisible();
  await expect(page.getByTestId('usage-mode-calls')).toHaveCount(0);
  await expect(page.getByTestId('usage-mode-minutes')).toHaveCount(0);
  await expect(page.locator('#usage-monthly-minutes')).toHaveCount(0);
  await expect(page.getByTestId('usage-compare')).toHaveCount(0);
  await expect(page.getByTestId('usage-share')).toHaveCount(0);
  await expect(page.getByTestId('usage-gst-ex')).toHaveCount(0);
  await expect(page).not.toHaveURL(/[?&]tier=/);

  await page.getByRole('button', { name: '500', exact: true }).click();
  await setRange(page, '#usage-minutes', 2);
  await expectMoneyClose(page.getByTestId('usage-estimate-total'), 5000);
  await expect(page.locator('.usage-breakdown dd')).toHaveCount(3);
});
