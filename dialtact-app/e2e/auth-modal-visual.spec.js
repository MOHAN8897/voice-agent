import { test, expect } from '@playwright/test';

test.describe('auth modal visual check', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('renders polished sign-in and signup states', async ({ page }, testInfo) => {
    const errors = [];
    page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
    page.on('console', (message) => {
      if (
        message.type() === 'error' &&
        !/Failed to load resource|ERR_CONNECTION_REFUSED|\[dialtact:api\] request_failed/.test(message.text())
      ) {
        errors.push(`console: ${message.text()}`);
      }
    });

    // The live effects (the test browser's software WebGL would get the recorded ones).
    await page.addInitScript(() => localStorage.setItem('dialtact:render', 'live'));
    // Signed out, the console sends you to the /signin page (it replaced the dialog).
    await page.goto('/#dashboard/overview');
    await expect(page).toHaveURL(/\/signin$/);
    await expect(page.getByTestId('auth-modal')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(900);

    await page.screenshot({ path: testInfo.outputPath('auth-modal-desktop.png') });

    const signin = page.getByTestId('signin-page');
    await expect(signin.getByRole('heading', { level: 1 })).toHaveText('Create your AI voice agent.');
    await expect(signin.getByText('Describe your business', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await expect(page.getByTestId('auth-modal').getByLabel('Work email')).toBeFocused();
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // The card sits in the right column, whole, over the drawing fibers; no light beam.
    const box = await page.getByTestId('auth-modal').boundingBox();
    expect(box.width).toBeGreaterThan(400);
    expect(box.x + box.width).toBeLessThanOrEqual(1440);
    await expect(signin.locator('.signin-bg canvas')).toHaveCount(1);
    await expect(signin.locator('canvas')).toHaveCount(1);

    // Black and white: the form's violet links and focus ring are neutral on the page.
    const accent = await page.getByRole('button', { name: 'Create an account' }).evaluate((el) => getComputedStyle(el).color);
    expect(accent).toBe('rgb(0, 0, 0)');

    await page.getByRole('button', { name: 'Create an account' }).click();
    await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
    await page.waitForTimeout(700);
    await page.screenshot({ path: testInfo.outputPath('auth-modal-signup.png') });

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent('dialtact:auth-error', {
          detail: { message: 'Incorrect email or password. Please try again.' },
        })
      );
    });
    await expect(page.getByRole('alert')).toContainText('Incorrect email or password');
    await page.waitForTimeout(300);
    await page.screenshot({ path: testInfo.outputPath('auth-modal-error.png') });

    expect(errors).toEqual([]);
  });

  test('fits a mobile viewport without overflow', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/#dashboard/overview');
    await expect(page.getByTestId('auth-modal')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(900);
    await page.screenshot({ path: testInfo.outputPath('auth-modal-mobile.png') });

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
