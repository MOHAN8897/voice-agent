import { test, expect } from '@playwright/test';

// Count real GPU draw submissions, not merely the presence of an empty canvas.
async function trackRendering(page) {
  await page.addInitScript(() => {
    window.__mascotDraws = 0;
    for (const method of ['drawElements', 'drawArrays']) {
      const original = WebGL2RenderingContext.prototype[method];
      WebGL2RenderingContext.prototype[method] = function (...args) {
        window.__mascotDraws += 1;
        return original.apply(this, args);
      };
    }
  });
}

test('StrictMode never updates an animation controller after disposal', async ({ page }) => {
  await page.addInitScript(() => { window.__disposedControllerUpdates = 0; window.__controllerUpdates = 0; });
  await page.route('**/src/three/BotController.js*', async route => {
    const response = await route.fetch();
    let body = await response.text();
    body = body.replace('update(delta) {', 'update(delta) { window.__controllerUpdates++; if (this.__testDisposed) window.__disposedControllerUpdates++;');
    body = body.replace('dispose() {', 'dispose() { this.__testDisposed = true;');
    await route.fulfill({ response, body });
  });
  await page.goto('/');
  await page.locator('canvas').first().scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__controllerUpdates)).toBeGreaterThan(10);
  expect(await page.evaluate(() => window.__disposedControllerUpdates)).toBe(0);
});

for (const [name, viewport, hasTouch] of [
  ['desktop', { width: 1440, height: 1000 }, false],
  ['tablet', { width: 820, height: 1180 }, true],
  ['phone', { width: 390, height: 844 }, true],
]) {
  test(`${name}: cold mascot load keeps rendering and responds after seven seconds`, async ({ browser }) => {
    const context = await browser.newContext({ viewport, hasTouch });
    const page = await context.newPage();
    try {
      await trackRendering(page);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto('/');
      const canvas = page.locator('canvas').first();
      await expect(canvas).toBeVisible({ timeout: 30000 });
      await canvas.scrollIntoViewIfNeeded();
      await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(0);
      await page.waitForTimeout(8000); // Regression: the old watchdog removed the scene at 7s.
      await expect(canvas).toBeVisible();
      const draws = await page.evaluate(() => window.__mascotDraws);
      await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(draws);
      if (hasTouch) await canvas.tap();
      else await canvas.click();
      await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });
}

test('a model taking over seven seconds still loads successfully', async ({ page }) => {
  await trackRendering(page);
  await page.route('**/models/*.glb*', async route => {
    await new Promise(resolve => setTimeout(resolve, 8500));
    await route.continue();
  });
  await page.goto('/');
  const canvas = page.locator('canvas').first();
  await canvas.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 30000 }).toBeGreaterThan(0);
  await expect(canvas).toBeVisible();
  await canvas.click();
  await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
});

for (const mode of ['no-webgl', 'reduced-motion', 'model-failure', 'context-loss']) {
  test(`${mode}: preview remains interactive`, async ({ page }) => {
    if (mode === 'no-webgl') {
      await page.addInitScript(() => {
        const original = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...args) {
          return type === 'webgl2' ? null : original.call(this, type, ...args);
        };
      });
    }
    if (mode === 'reduced-motion') await page.emulateMedia({ reducedMotion: 'reduce' });
    if (mode === 'model-failure') await page.route('**/models/*.glb*', route => route.abort());
    await page.goto('/');
    if (mode === 'context-loss') {
      const canvas = page.locator('canvas').first();
      await expect(canvas).toBeVisible();
      await canvas.evaluate(element => element.dispatchEvent(new Event('webglcontextlost', { cancelable: true })));
    }
    const preview = page.getByRole('button', { name: 'Interact with Dialtact' }).first();
    await expect(preview).toBeVisible({ timeout: 30000 });
    await preview.click();
    await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
  });
}
