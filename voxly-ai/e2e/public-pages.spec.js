import { test, expect } from '@playwright/test';
const pages = [['/support', 'Customer Support & Contact'], ['/company', 'About Dialtact'], ['/privacy', 'Privacy Policy'], ['/terms', 'Terms of Service'], ['/security', 'Security']];
for (const width of [390, 820, 1440]) {
  test(`public routes have correct metadata and fit at width ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.route('**/api/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthenticated isolated audit"}' }));
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    for (const [route, title] of pages) {
      await page.goto(route);
      await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
      await expect(page).toHaveTitle(new RegExp(title));
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', `https://www.dialtact.com${route}`);
      await expect(page.locator('meta[name="robots"]')).toHaveCount(1);
      await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /index, follow/);
      await expect(page.locator('main')).toBeVisible();
      if (route === '/support') {
        await expect(page.getByText('All Trunks & Core Systems Active', { exact: true })).toHaveCount(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
    expect(errors).toEqual([]);
  });
}

test('footer navigation has crawlable public URLs and browser back restores route metadata', async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }));
  await page.goto('/support');
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  const privacy = page.getByRole('link', { name: 'Privacy Policy', exact: true }).first();
  await expect(privacy).toHaveAttribute('href', '/privacy');
  await privacy.click();
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(page).toHaveTitle(/Privacy Policy/);
  await page.goBack();
  await expect(page).toHaveTitle(/Customer Support/);
});


test('production HTML includes public content and distinct canonical URLs before JavaScript', async () => {
  const fs = await import('node:fs/promises');
  for (const [route] of pages) {
    const html = await fs.readFile(new URL(`../dist${route}/index.html`, import.meta.url), 'utf8');
    expect(html).toContain(`<link rel="canonical" href="https://www.dialtact.com${route}"`);
    expect(html).toMatch(/<div id="root"><div/);
    expect(html).toMatch(/<main[ >]/);
    expect(html).toMatch(/<h1[ >]/);
  }
});
