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

function mascotCanvas(page) {
  return page.locator('[data-mascot-state] canvas').first();
}

test('a real lost WebGL context restores the same canvas and resumes rendering', async ({ page }) => {
  await trackRendering(page);
  await page.goto('/');
  const canvas = mascotCanvas(page);
  await canvas.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(0);
  await canvas.evaluate(element => {
    window.__originalMascotCanvas = element;
    window.__lostContext = element.getContext('webgl2').getExtension('WEBGL_lose_context');
    window.__lostContext.loseContext();
  });
  await expect(page.getByText('Restoring 3D animation…', { exact: true })).toBeVisible();
  await page.evaluate(() => window.__lostContext.restoreContext());
  await expect(page.locator('[data-mascot-state="active"]')).toBeVisible();
  expect(await canvas.evaluate(element => element === window.__originalMascotCanvas)).toBe(true);
  const draws = await page.evaluate(() => window.__mascotDraws);
  await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(draws);
});

test('failed model requests can be retried without reloading the page', async ({ page }) => {
  await trackRendering(page);
  await page.route('**/models/*.glb*', route => route.abort());
  await page.goto('/');
  await expect(page.getByText('3D could not load. Please try again.')).toBeVisible();
  await page.unroute('**/models/*.glb*');
  await page.getByRole('button', { name: 'Retry 3D' }).click();
  await mascotCanvas(page).scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 15000 }).toBeGreaterThan(0);
});

test('scrolling and page visibility resume rendering after a pause', async ({ page }) => {
  await trackRendering(page);
  await page.goto('/');
  const canvas = mascotCanvas(page);
  await canvas.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(0);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(page.locator('[data-mascot-state="paused"]')).toBeAttached();
  await canvas.scrollIntoViewIfNeeded();
  await expect(page.locator('[data-mascot-state="active"]')).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('[data-mascot-state="paused"]')).toBeVisible();
  await page.evaluate(() => {
    delete document.hidden;
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
  });
  await page.setViewportSize({ width: 390, height: 700 });
  await canvas.scrollIntoViewIfNeeded();
  await expect(page.locator('[data-mascot-state="active"]')).toBeVisible();
  const draws = await page.evaluate(() => window.__mascotDraws);
  await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(draws);
});

test('touch devices never steer the model and canceled scroll gestures never activate it', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 3 });
  const page = await context.newPage();
  try {
    await page.addInitScript(() => { window.__pointerValues = []; });
    await page.route('**/src/three/BotController.js*', async route => {
      const response = await route.fetch();
      const body = (await response.text()).replace('setPointer(x, y) {', 'setPointer(x, y) { window.__pointerValues.push([x, y]);');
      await route.fulfill({ response, body });
    });
    await page.goto('/');
    const canvas = mascotCanvas(page);
    await canvas.scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => window.__pointerValues.length)).toBeGreaterThan(5);
    await canvas.dispatchEvent('pointerdown', { pointerType: 'touch', clientX: 100, clientY: 100 });
    await canvas.dispatchEvent('pointermove', { pointerType: 'touch', clientX: 250, clientY: 150 });
    await canvas.dispatchEvent('pointercancel', { pointerType: 'touch' });
    await page.mouse.move(380, 100);
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => window.__pointerValues.every(([x, y]) => x === 0 && y === 0))).toBe(true);
    await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toHaveCount(0);
    expect(await canvas.evaluate(element => element.width / element.getBoundingClientRect().width)).toBeLessThanOrEqual(1.01);
    await canvas.tap();
    await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
    // Slow devices can deliver the compatibility click after the 350ms debounce.
    await page.waitForTimeout(450);
    await canvas.evaluate(element => {
      const rect = element.getBoundingClientRect();
      element.dispatchEvent(new PointerEvent('click', { bubbles: true, pointerType: 'touch',
        clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }));
    });
    await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
  } finally { await context.close(); }
});

test('data saver explains the preview and allows an explicit 3D retry', async ({ page }) => {
  await trackRendering(page);
  await page.addInitScript(() => Object.defineProperty(navigator, 'connection', { value: { saveData: true }, configurable: true }));
  await page.goto('/');
  await expect(page.getByText('Data saver is on. Retry 3D to load the animation.')).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
  await page.getByRole('button', { name: 'Retry 3D' }).click();
  await mascotCanvas(page).scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 15000 }).toBeGreaterThan(0);
});

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
  await mascotCanvas(page).scrollIntoViewIfNeeded();
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
      const canvas = mascotCanvas(page);
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
  const canvas = mascotCanvas(page);
  await canvas.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 30000 }).toBeGreaterThan(0);
  await expect(canvas).toBeVisible();
  await canvas.click();
  await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
});

test('a model that finishes after the recovery preview appears automatically replaces it', async ({ page }) => {
  await trackRendering(page);
  let releaseRequest;
  let onRequestStarted;
  const requestStarted = new Promise(resolve => { onRequestStarted = resolve; });
  const requestGate = new Promise(resolve => { releaseRequest = resolve; });
  await page.route('**/models/*.glb*', async route => {
    onRequestStarted();
    await requestGate;
    await route.continue();
  });
  await page.goto('/');
  await requestStarted;
  await expect(page.getByText('3D is taking longer than usual.', { exact: false })).toBeVisible({ timeout: 20000 });
  const preview = page.getByRole('button', { name: 'Interact with Dialtact' }).first();
  await expect(preview.locator('img')).toBeVisible();
  expect(await preview.locator('img').evaluate(image => image.naturalWidth)).toBeGreaterThan(0);

  releaseRequest();
  await expect(page.locator('[data-mascot-state="active"]')).toBeVisible({ timeout: 30000 });
  await expect(page.getByText('3D is taking longer than usual.', { exact: false })).toHaveCount(0);
});

test('a stalled model can be retried without reloading the page', async ({ page }) => {
  await trackRendering(page);
  let releaseRequest;
  let requestCount = 0;
  let onFirstRequest;
  const firstRequest = new Promise(resolve => { onFirstRequest = resolve; });
  const requestGate = new Promise(resolve => { releaseRequest = resolve; });
  await page.route('**/models/*.glb*', async route => {
    requestCount += 1;
    if (requestCount === 1) {
      onFirstRequest();
      await requestGate;
      await route.abort();
      return;
    }
    await route.continue();
  });
  await page.goto('/');
  await firstRequest;
  await expect(page.getByText('3D is taking longer than usual.', { exact: false })).toBeVisible({ timeout: 20000 });

  releaseRequest();
  const retry = page.getByRole('button', { name: 'Retry 3D' }).first();
  await expect(retry).toBeVisible();
  await page.unroute('**/models/*.glb*');
  await retry.click();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 30000 }).toBeGreaterThan(0);
});

test('reduced-motion preference keeps the 3D model available in its low-motion mode', async ({ page }) => {
  await trackRendering(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const canvas = mascotCanvas(page);
  await expect(canvas).toBeVisible({ timeout: 30000 });
  await canvas.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => window.__mascotDraws), { timeout: 15000 }).toBeGreaterThan(0);
  await expect(page.locator('[data-mascot-state="active"]')).toBeVisible();
  await expect(page.getByText('Animation is off in your reduced-motion settings.')).toHaveCount(0);
});

for (const mode of ['no-webgl', 'model-failure', 'context-loss']) {
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
    if (mode === 'context-loss') await trackRendering(page);
    await page.goto('/');
    if (mode === 'context-loss') {
      const canvas = mascotCanvas(page);
      await expect(canvas).toBeVisible();
      await expect.poll(() => page.evaluate(() => window.__mascotDraws)).toBeGreaterThan(0);
      const handled = await canvas.evaluate(element => {
        const event = new Event('webglcontextlost', { cancelable: true });
        element.dispatchEvent(event);
        return event.defaultPrevented;
      });
      expect(handled).toBe(true);
      await expect(page.locator('[data-mascot-state="recovering"]')).toBeVisible();
    }
    const preview = page.getByRole('button', { name: 'Interact with Dialtact' }).first();
    await expect(preview).toBeVisible({ timeout: 30000 });
    await expect(preview.locator('img')).toHaveAttribute('src', '/images/Dialtact_call_assistant_fallback.png');
    await expect.poll(() => preview.locator('img').evaluate(image => image.naturalWidth)).toBeGreaterThan(0);
    await preview.click();
    await expect(page.getByText("Hello! Hiii! 👋 I'm Dialtact! Nice to meet you!", { exact: true })).toBeVisible();
  });
}
