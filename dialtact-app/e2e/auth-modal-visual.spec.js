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

    await page.goto('/#dashboard/overview');
    await expect(page.getByTestId('auth-modal')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(900);

    await page.screenshot({ path: testInfo.outputPath('auth-modal-desktop.png') });

    const phoneFeature = page.getByText('Live voice on real phone lines', { exact: true });
    await expect(phoneFeature).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Sign in to your console' })).toBeVisible();
    await expect(page.getByTestId('auth-modal').getByLabel('Work email')).toBeFocused();

    const box = await page.getByTestId('auth-modal').boundingBox();
    expect(box.width).toBeGreaterThan(900);

    const design = await page.evaluate(() => ({
      dmSansLoaded: document.fonts.check('500 13px "DM Sans"'),
      instrumentSerifLoaded: document.fonts.check('italic 16px "Instrument Serif"'),
      dialogAnimation: getComputedStyle(document.querySelector('.auth-dialog')).animationName,
      waveAnimation: getComputedStyle(document.querySelector('.auth-wave')).animationName,
    }));
    expect(design.dmSansLoaded).toBe(true);
    expect(design.instrumentSerifLoaded).toBe(true);
    expect(design.dialogAnimation).toBe('auth-dialog-in');
    expect(design.waveAnimation).toBe('auth-wave');

    await page.emulateMedia({ reducedMotion: 'reduce' });
    const reducedMotion = await page.evaluate(() => ({
      dialog: getComputedStyle(document.querySelector('.auth-dialog')).animationName,
      wave: getComputedStyle(document.querySelector('.auth-wave')).animationName,
    }));
    expect(reducedMotion.dialog).toBe('none');
    expect(reducedMotion.wave).toBe('none');

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
