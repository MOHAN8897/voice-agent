import { test, expect } from '@playwright/test';

async function expectAudioPlaying(page) {
  await expect.poll(() => page.locator('.landing-player audio').evaluate(audio => ({
    paused: audio.paused, started: audio.currentTime > 0, error: audio.error?.message || null,
    ready: audio.readyState, status: document.querySelector('.landing-audio-status').textContent,
  }))).toMatchObject({ paused: false, started: true, error: null });
}

async function openLanding(page) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const body = path === '/api/auth/session' ? { authenticated: false, saas_auth_enabled: true }
      : path.includes('/support/config') ? { socialLinks: {} } : { ok: true, items: [] };
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.addStyleTag({ content: '[data-reticle-overlay] { display:none!important; }' });
  await expect(page.getByTestId('landing-refresh')).toBeVisible();
}

test('the hero stays first, all compact navigation targets work, and sample workspace loads', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openLanding(page);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Your AI employee');
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  for (const [label, id] of [['Product', 'capabilities'], ['Use cases', 'industries'], ['How it works', 'how-it-works'], ['Pricing', 'pricing'], ['FAQ', 'faq']]) {
    await page.locator('header nav').getByRole('link', { name: label, exact: true }).click();
    await expect(page.locator(`#${id}`)).toBeInViewport();
  }
  const preview = page.getByRole('img', { name: /Dialtact lead workspace/ });
  await preview.scrollIntoViewIfNeeded();
  await expect.poll(() => preview.evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
  expect(errors).toEqual([]);
  expect(await page.locator('body').innerText()).not.toMatch(/Annual Billing|-20%|100,000|SOC.?2 certified/);
});

test('workflow choices change the explanation and support keyboard use', async ({ page }) => {
  await openLanding(page);
  const support = page.getByRole('button', { name: 'Customer support', exact: true });
  await support.click();
  await expect(support).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('heading', { name: 'Make the first conversation count' })).toBeVisible();
  const campaigns = page.getByRole('button', { name: 'Outbound campaigns', exact: true });
  await campaigns.focus();
  await page.keyboard.press('Enter');
  await expect(campaigns).toHaveAttribute('aria-pressed', 'true');
  await expect(support).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByText('A campaign you can inspect, call by call.', { exact: true })).toBeVisible();
});

test('voice samples play real audio, stop, and switch industry without overlapping', async ({ page }) => {
  await openLanding(page);
  await page.getByRole('button', { name: 'Play voice sample', exact: true }).click();
  await expectAudioPlaying(page);
  await page.getByRole('button', { name: 'Stop voice sample', exact: true }).click();
  await expect.poll(() => page.locator('.landing-player audio').evaluate(audio => audio.paused)).toBe(true);
  await page.getByLabel('Choose a sample').selectOption('education');
  await expect(page.locator('.landing-player blockquote')).toContainText('Northbridge Institute');
  await expect(page.locator('.landing-player audio')).toHaveAttribute('src', '/audio/dialtact/samples/education.wav');
  await expect(page.getByRole('button', { name: 'Play voice sample', exact: true })).toBeVisible();
});

test('unavailable sample shows recovery and can play after retry', async ({ page }) => {
  await openLanding(page);
  await page.route('**/audio/dialtact/samples/real-estate.wav', route => route.fulfill({ status: 404, body: '' }));
  await page.getByRole('button', { name: 'Play voice sample', exact: true }).click();
  await expect(page.locator('.landing-audio-status')).toContainText(/Audio.*(unavailable|could not start)/);
  await page.unroute('**/audio/dialtact/samples/real-estate.wav');
  await page.getByLabel('Choose a sample').selectOption('education');
  await page.getByRole('button', { name: 'Play voice sample', exact: true }).click();
  await expectAudioPlaying(page);
});

test('pricing preserves its intended destination through sign-in', async ({ page }) => {
  await openLanding(page);
  await page.getByRole('button', { name: 'Explore workspace pricing', exact: true }).click();
  await expect(page.getByTestId('auth-modal')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('dialtact_post_auth_tab'))).toBe('billing');
});

test('integration exploration opens its intended workspace after sign-in', async ({ page }) => {
  await openLanding(page);
  await page.getByRole('button', { name: 'Explore integrations', exact: true }).click();
  await expect(page.getByTestId('auth-modal')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('dialtact_post_auth_tab'))).toBe('integrations');
});

test('mobile layout, native FAQ keyboard control and closing action remain accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page);
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await page.locator('header').getByRole('link', { name: 'Product', exact: true }).click();
  await expect(page.locator('#capabilities')).toBeInViewport();
  const question = page.locator('summary').filter({ hasText: 'What happens after the call?' });
  await question.focus();
  await page.keyboard.press('Enter');
  await expect(question.locator('..')).toHaveAttribute('open', '');
  await expect(question.locator('..')).toContainText('do not automatically schedule a redial');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.landing-final').getByRole('button', { name: 'Build your agent' }).click();
  await expect(page.getByTestId('auth-modal')).toBeVisible();
});
