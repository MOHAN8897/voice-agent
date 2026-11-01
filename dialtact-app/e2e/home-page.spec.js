import { test, expect } from '@playwright/test';

// The current home page (src/marketing). The previous one lives at /legacy and is
// covered by landing-refresh.spec.js and mascot-loading.spec.js.

const CATALOG = {
  currency: 'USD',
  plans: [],
  numberSkus: [{ country: 'IN', currency: 'USD', monthlyCents: 40000, monthlyUsd: 4, monthlyInr: 564 }],
  rates: { fxRateInr: 94 },
  tax: { enabled: true, ratePercent: 18, priceIncludesTax: false, countryCode: 'IN' },
  calculator: { allowMinuteInput: true, compareTiers: true, shareableEstimate: true, showGstToggle: true },
  tiers: [
    { id: 'alpha', label: 'Alpha tier', featured: false, visible: true, tags: [{ label: 'Alpha tag', tone: 'accent' }], pstn: { usdPerMin: 0.05, inrPerMin: 5 } },
    { id: 'beta', label: 'Beta tier', featured: true, visible: true, tags: [], pstn: { usdPerMin: 0.07, inrPerMin: 7 } },
  ],
};

async function openHome(page, path = '/', { motion = false, render = 'live' } = {}) {
  // Reduced motion by default: no smooth-scroll inertia or pinning, so positions are exact.
  await page.emulateMedia({ reducedMotion: motion ? 'no-preference' : 'reduce' });
  // The test browser renders WebGL in software, which the page would answer with the
  // recorded mascot; most tests are about the live one. `render: null` lets the page decide.
  if (render) await page.addInitScript((mode) => localStorage.setItem('dialtact:render', mode), render);
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname;
    const body = url === '/api/auth/session' ? { authenticated: false, saas_auth_enabled: true }
      : url.includes('/support/config') ? { socialLinks: {} }
      : url.includes('/billing/catalog') ? CATALOG
      : { ok: true, items: [] };
    await route.fulfill({ json: body });
  });
  await page.goto(path);
  await page.addStyleTag({ content: '[data-reticle-overlay] { display:none!important; }' });
  if (path === '/') await expect(page.locator('.mk')).toBeVisible();
}

/** Scroll so an element's top meets the top of the viewport (offsetTop is parent-relative). */
async function scrollToTop(page, selector) {
  await page.locator(selector).evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY));
}

test('one hero heading, every nav link reaches its section, and no junk links', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await openHome(page);
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('AI voice agents that answer every call.');

  for (const [label, id] of [['Product', 'capabilities'], ['Use cases', 'industries'], ['How it works', 'how-it-works'], ['Pricing', 'pricing'], ['FAQ', 'faq']]) {
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/#${id}$`));
    await expect(page.locator(`#${id}`)).toBeInViewport();
  }

  // Every link is a real destination: root-relative, external https, or the skip link.
  const hrefs = await page.locator('a[href]').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
  const junk = hrefs.filter((href) => !(href === '#main' || /^\/(?!\/)/.test(href) || /^https:\/\//.test(href)));
  expect(junk).toEqual([]);
  expect(hrefs).not.toContain('/pricing');
  expect(errors).toEqual([]);
});

test('search metadata: home is indexable with FAQ data; /legacy is noindex and canonical to /', async ({ page }) => {
  await openHome(page);
  await expect(page).toHaveTitle('Dialtact — AI Voice Agents for Customer Calls');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://www.dialtact.com/');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /^index, follow/);

  const faq = JSON.parse(await page.locator('#faq script[type="application/ld+json"]').textContent());
  expect(faq['@type']).toBe('FAQPage');
  const questions = await page.locator('#faq .mk-faq-item button').allInnerTexts();
  expect(faq.mainEntity.map((entry) => entry.name)).toEqual(questions.map((text) => text.trim()));

  await page.goto('/legacy');
  await expect(page.getByTestId('landing-refresh')).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://www.dialtact.com/');
});

test('a section link on another page opens that section of the home page', async ({ page }) => {
  await openHome(page, '/support');
  await page.locator('a[href="/#pricing"]').first().click();
  await expect(page).toHaveURL(/\/#pricing$/);
  await expect(page.locator('.mk')).toBeVisible();
  await expect(page.locator('#pricing')).toBeInViewport();
});

test('the real-call demo plays audio, writes the log, and the mascot takes the call', async ({ page }) => {
  await openHome(page);
  await page.locator('#demo').scrollIntoViewIfNeeded();
  await page.getByTestId('mk-demo-play').click();
  await expect(page.locator('.mk-live-badge')).toHaveText('LIVE');
  await expect(page.locator('.mk-bot-bubble')).toContainText('On a call');
  await expect.poll(() => page.locator('.mk-call-log .mk-log-line').count()).toBeGreaterThan(1);
  await expect(page.locator('.mk-spoken')).not.toBeEmpty();

  await page.getByTestId('mk-demo-play').click();
  await expect(page.locator('.mk-live-badge')).toHaveText('READY');

  // Choosing another sample swaps the script without playing over the first.
  await page.getByRole('button', { name: 'Test drive booking', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test drive booking', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.mk-call-meta')).toContainText('Car Dealership');
});

test('the capability wheel turns with the keyboard and the card follows', async ({ page }) => {
  await openHome(page);
  const wheel = page.getByRole('listbox', { name: 'Capabilities' });
  await wheel.scrollIntoViewIfNeeded();
  const first = await page.locator('.mk-reflect h3').first().innerText();
  await wheel.focus();
  await page.keyboard.press('ArrowDown');
  const selected = wheel.getByRole('option', { selected: true });
  await expect(selected).not.toHaveText(first);
  await expect(page.locator('#capabilities .mk-reflect h3')).not.toHaveText(first);
  await expect(page.locator('#capabilities .mk-reflect h3')).toHaveText((await selected.innerText()).trim());
});

test('the use-case carousel moves with its controls', async ({ page }) => {
  await openHome(page);
  const carousel = page.locator('#industries');
  await carousel.scrollIntoViewIfNeeded();
  const previous = carousel.getByRole('button', { name: 'Previous industry' });
  await expect(previous).toBeDisabled();
  await carousel.getByRole('button', { name: 'Next industry' }).click();
  await expect(previous).toBeEnabled();
  await expect(carousel.getByRole('button', { name: 'Go to slide 2' })).toHaveAttribute('aria-current', 'true');
});

test('FAQ answers expand and collapse', async ({ page }) => {
  await openHome(page);
  const question = page.getByRole('button', { name: 'What happens after the call?' });
  await question.scrollIntoViewIfNeeded();
  await expect(question).toHaveAttribute('aria-expanded', 'false');
  await question.click();
  await expect(question).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#faq')).toContainText('do not automatically schedule a redial');
  await question.click();
  await expect(question).toHaveAttribute('aria-expanded', 'false');
});

test('the mascot stands in a section slot on desktop and docks when the slot scrolls away', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page);
  const bot = page.getByTestId('scroll-bot');
  await scrollToTop(page, '#how-it-works');
  await expect(bot).toHaveAttribute('data-docked', 'false');
  // It sits inside the section's slot, not over the copy (once it has faded over).
  await expect(bot).toHaveAttribute('data-arrived', 'true');
  const slot = await page.locator('#how-it-works .mk-bot-anchor').boundingBox();
  const box = await bot.boundingBox();
  expect(Math.abs(box.x - slot.x)).toBeLessThan(slot.width);
  expect(Math.abs(box.y - slot.y)).toBeLessThan(slot.height);

  await scrollToTop(page, '#usage-calculator');
  await expect(bot).toHaveAttribute('data-docked', 'true');
});

test('pricing shows the published tiers and keeps the billing destination through sign-in', async ({ page }) => {
  await openHome(page);
  const cards = page.getByTestId('mk-pricing-cards');
  await cards.scrollIntoViewIfNeeded();
  await expect(cards.locator('[data-tier]')).toHaveCount(2);
  await expect(cards.locator('[data-tier="alpha"]')).toContainText('₹5.00');
  await expect(cards.locator('[data-tier="alpha"] .mk-price-tags li')).toHaveText(['Alpha tag']);
  await cards.getByRole('button', { name: /Choose Beta tier/ }).click();
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByTestId('auth-modal')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('dialtact_post_auth_tab'))).toBe('billing');
});

test('phone layout has no horizontal overflow anywhere down the page', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await openHome(page);
  const height = await page.evaluate(() => document.body.scrollHeight);
  for (let y = 0; y < height; y += 700) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('the 3D mascot loads (no flat picture) and performs its Blender gestures as it lands', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page, '/', { motion: true });
  const bot = page.getByTestId('scroll-bot');
  // While it boots, the recorded mascot stands in, never the flat PNG; then the live one takes over.
  await expect(bot.locator('img[src*="call_assistant_fallback"]')).toHaveCount(0);
  await expect(bot.locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 20000 });
  await expect(bot).toHaveAttribute('data-render', 'live');
  await expect(bot.locator('.mk-bot-video')).toHaveCount(0);

  // Land in "How it works": glide over, reach out to the steps on its right, then listen.
  const moves = [];
  await page.exposeFunction('__recordMove', (move) => moves.push(move));
  await bot.evaluate((el) => new MutationObserver(() => window.__recordMove(el.dataset.botMove))
    .observe(el, { attributes: true, attributeFilter: ['data-bot-move'] }));
  await page.locator('#how-it-works').evaluate((el) => window.__dialtactLenis.scrollTo(el, { offset: -40, immediate: true }));
  await expect(bot).toHaveAttribute('data-docked', 'false');
  await expect.poll(() => moves.join(','), { timeout: 8000 }).toContain('REACH_RIGHT,LISTENING');
});

test('a lost GPU context never leaves the mascot as a picture', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page, '/', { motion: true });
  const bot = page.getByTestId('scroll-bot');
  const canvas = bot.locator('[data-mascot-state] canvas');
  await expect(bot.locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 20000 });

  // Record every state and any picture the mascot shows, so a brief state is not missed.
  await bot.evaluate((el) => {
    window.__mascotStates = [];
    window.__pictureShown = false;
    new MutationObserver(() => {
      const state = el.querySelector('[data-mascot-state]')?.dataset.mascotState;
      if (state && window.__mascotStates.at(-1) !== state) window.__mascotStates.push(state);
      if (el.querySelector('img[src*="call_assistant_fallback"]')) window.__pictureShown = true;
      if (el.innerText.includes('Restoring 3D animation')) window.__restoringShown = true;
    }).observe(el, { subtree: true, childList: true, attributes: true, characterData: true });
  });

  // The browser restores the context: the same canvas comes back.
  await canvas.evaluate((el) => {
    window.__mascotCanvas = el;
    window.__lose = el.getContext('webgl2').getExtension('WEBGL_lose_context');
    window.__lose.loseContext();
  });
  await expect.poll(() => page.evaluate(() => window.__restoringShown === true)).toBe(true);
  await page.evaluate(() => window.__lose.restoreContext());
  await expect(bot.locator('[data-mascot-state="active"]')).toBeVisible();
  expect(await canvas.evaluate((el) => el === window.__mascotCanvas)).toBe(true);

  // The browser never restores it: a fresh renderer is built automatically.
  await canvas.evaluate((el) => el.getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
  await expect.poll(() => page.evaluate(() => window.__mascotStates.filter((x) => x === 'recovering').length)).toBe(2);
  await expect(bot.locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 10000 });
  expect(await bot.locator('[data-mascot-state] canvas').evaluate((el) => el !== window.__mascotCanvas)).toBe(true);
  expect(await page.evaluate(() => window.__pictureShown)).toBe(false);
});

test('the mascot opens big on the right, comes to the centre, then works the left side', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page);
  const bot = page.getByTestId('scroll-bot');
  const centreX = async () => bot.evaluate((el) => { const r = el.getBoundingClientRect(); return r.x + r.width / 2; });
  await expect(bot).toHaveAttribute('data-docked', 'false');
  const hero = await bot.boundingBox();
  expect(await centreX()).toBeGreaterThan(1440 * 0.6);
  await scrollToTop(page, '.mk-statement');
  await expect.poll(centreX).toBeGreaterThan(1440 * 0.4);
  await expect.poll(centreX).toBeLessThan(1440 * 0.6);
  await scrollToTop(page, '#how-it-works');
  await expect.poll(centreX).toBeLessThan(1440 * 0.4);
  // It is largest in the hero.
  const later = await bot.boundingBox();
  expect(hero.width).toBeGreaterThan(later.width);
});

test('a tab left open across a new build reloads once and shows the 3D mascot', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  // The first request for the scene's code fails the way a deleted build chunk does.
  let failed = false;
  await page.route('**/src/three/DialtactScene.jsx*', (route) => {
    if (failed) return route.continue();
    failed = true;
    return route.fulfill({ status: 404, body: '' });
  });
  await openHome(page, '/', { motion: true });
  await expect(page.getByTestId('scroll-bot').locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 30000 });
  expect(failed).toBe(true);
  await expect(page.getByText('3D could not load. Please try again.')).toHaveCount(0);
});

test('the mascot glides between sections instead of jumping', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page, '/', { motion: true });
  const bot = page.getByTestId('scroll-bot');
  await expect(bot).toHaveAttribute('data-arrived', 'true');
  const x = () => bot.evaluate((el) => el.getBoundingClientRect().x);
  const start = await x();
  // Time how long it takes to arrive in the next slot, measured in the page.
  const travelMs = page.evaluate(() => new Promise((resolve) => {
    const el = document.querySelector('[data-testid=scroll-bot]');
    const t0 = performance.now();
    let left = false;
    const observer = new MutationObserver(() => {
      if (el.dataset.arrived === 'false') left = true;
      if (left && el.dataset.arrived === 'true') { observer.disconnect(); resolve(performance.now() - t0); }
    });
    observer.observe(el, { attributes: true, attributeFilter: ['data-arrived'] });
  }));
  await page.locator('#how-it-works').evaluate((el) => window.__dialtactLenis.scrollTo(el, { offset: -60, immediate: true }));
  // Mid-flight it is somewhere between the two slots, not at either.
  await page.waitForTimeout(250);
  const mid = await x();
  expect(Math.abs(mid - start)).toBeGreaterThan(20);
  expect(await travelMs).toBeGreaterThan(600);
  expect(Math.abs((await x()) - mid)).toBeGreaterThan(20);
});

test('Create your own agent opens the sign-in page, not a dialog', async ({ page }) => {
  await openHome(page);
  await page.getByRole('link', { name: 'Create your own agent' }).first().click();
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page).toHaveTitle('Create your agent — Dialtact');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  const signin = page.getByTestId('signin-page');
  await expect(signin.getByRole('heading', { level: 1 })).toHaveText('Create your AI voice agent.');
  // New visitors start on sign-up; the laser and the fibers are real canvases.
  await expect(page.getByTestId('auth-modal').getByRole('heading', { name: 'Create your account' })).toBeVisible();
  await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  await expect(signin.locator('.signin-laser canvas')).toHaveCount(1);
  await expect(signin.locator('.signin-bg canvas')).toHaveCount(1);
  await signin.getByRole('link', { name: 'Back to home' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('.mk-hero')).toBeVisible();
});

test('signing in on the page opens the agent builder', async ({ page }) => {
  const user = { userId: 'page-user', fullName: 'Page Tester', email: 'page@example.invalid', hasCompletedOnboarding: true };
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const accessToken = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  const auth = { user, tenant: { tenantId: 'page-tenant', name: 'Page Workspace' }, role: 'owner', accessToken,
    sessionPolicy: { idleTimeoutMinutes: 360, absoluteMaxHours: 24, accessTokenMinutes: 15 } };
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = { ok: true, items: [] };
    if (['/api/auth/login', '/api/auth/me'].includes(path)) data = auth;
    else if (path === '/api/auth/session') data = { authenticated: false, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [] };
    else if (path.includes('/billing/catalog')) data = CATALOG;
    await route.fulfill({ json: data });
  });
  await page.addInitScript(() => localStorage.setItem('dialtact_tour_completed_page@example.invalid', 'true'));
  await page.goto('/signin');
  const form = page.getByTestId('auth-modal');
  await form.getByLabel('Work email').fill(user.email);
  await form.getByLabel('Password', { exact: true }).fill('test-only-password');
  await form.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/#dashboard\/employees$/);
  await expect(page.getByRole('button', { name: /Create AI employee/i }).first()).toBeVisible();
  await expect(page.getByTestId('signin-page')).toHaveCount(0);
});

test('with reduced motion on, the mascot fades between sections and still gestures', async ({ page }) => {
  // Windows "Animation effects" off makes Chrome report reduced motion. The page then
  // fades the mascot over instead of flying it, but it never freezes.
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page);
  const bot = page.getByTestId('scroll-bot');
  await expect(bot.locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 20000 });
  await expect(bot).toHaveAttribute('data-arrived', 'true');
  const moves = [];
  await page.exposeFunction('__recordMove', (move) => moves.push(move));
  await bot.evaluate((el) => {
    const tilt = el.querySelector('.mk-bot-tilt');
    window.__minOpacity = 1;
    const watch = () => {
      window.__minOpacity = Math.min(window.__minOpacity, Number(tilt.style.opacity || 1));
      requestAnimationFrame(watch);
    };
    watch();
    new MutationObserver(() => window.__recordMove(el.dataset.botMove))
      .observe(el, { attributes: true, attributeFilter: ['data-bot-move'] });
  });
  await scrollToTop(page, '#how-it-works');
  await expect.poll(() => moves.join(','), { timeout: 8000 }).toContain('REACH_RIGHT,LISTENING');
  expect(await page.evaluate(() => window.__minOpacity)).toBeLessThan(0.2);
  await expect.poll(() => bot.locator('.mk-bot-tilt').evaluate((el) => el.style.opacity)).toBe('');
});

test('tapping the mascot reacts to where it was tapped', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page, '/', { motion: true });
  const bot = page.getByTestId('scroll-bot');
  await expect(bot.locator('[data-mascot-state="active"] canvas')).toBeVisible({ timeout: 20000 });
  await expect(bot).toHaveAttribute('data-arrived', 'true');
  // Tap once the body has stopped moving (it springs, and the hero may still be settling).
  const tap = async (fx, fy) => {
    let box = null;
    for (let i = 0; i < 40; i += 1) {
      const next = await page.locator('.mk-bot-hit').boundingBox();
      const still = box && Math.abs(next.x - box.x) < 1 && Math.abs(next.y - box.y) < 1 && Math.abs(next.height - box.height) < 1;
      box = next;
      if (still) break;
      await page.waitForTimeout(120);
    }
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
  };

  await tap(0.5, 0.12);
  await expect(bot).toHaveAttribute('data-bot-tap', 'Hey, that tickles.');
  await expect(page.locator('.mk-bot-bubble')).toContainText('Hey, that tickles.');
  await expect(page.locator('.mk-bot-burst')).toHaveCount(1);
  await page.waitForTimeout(1800);

  // The feet: it jumps, so its body leaves the ground and lands back.
  await bot.locator('.mk-bot-tilt').evaluate((el) => {
    window.__lowest = 0;
    const watch = () => {
      window.__lowest = Math.min(window.__lowest, new DOMMatrix(getComputedStyle(el).transform).m42);
      requestAnimationFrame(watch);
    };
    watch();
  });
  await tap(0.5, 0.88);
  await expect(bot).toHaveAttribute('data-bot-tap', 'First ring. Every time.');
  await expect.poll(() => page.evaluate(() => window.__lowest)).toBeLessThan(-10);
  await expect.poll(() => bot.locator('.mk-bot-tilt').evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).m42)).toBe(0);
  await page.waitForTimeout(1800);

  // Three quick taps: it celebrates.
  await tap(0.5, 0.5);
  const box = await page.locator('.mk-bot-hit').boundingBox();
  for (let i = 0; i < 2; i += 1) await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(bot).toHaveAttribute('data-bot-tap', "Okay, okay. I'm awake!");
  await expect(bot).toHaveAttribute('data-bot-move', 'CELEBRATE');
});

test('the nav has one account button: Log in, then the console', async ({ page }) => {
  const user = { userId: 'nav-user', fullName: 'Nav Tester', email: 'nav@example.invalid', hasCompletedOnboarding: true };
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const accessToken = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  const auth = { user, tenant: { tenantId: 'nav-tenant', name: 'Nav Workspace' }, role: 'owner', accessToken,
    sessionPolicy: { idleTimeoutMinutes: 360, absoluteMaxHours: 24, accessTokenMinutes: 15 } };
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = { ok: true, items: [] };
    if (['/api/auth/login', '/api/auth/me'].includes(path)) data = auth;
    else if (path === '/api/auth/session') data = { authenticated: false, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [] };
    else if (path.includes('/billing/catalog')) data = CATALOG;
    await route.fulfill({ json: data });
  });
  await page.addInitScript(() => localStorage.setItem('dialtact_tour_completed_nav@example.invalid', 'true'));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const actions = page.locator('.mk-nav-actions button');
  await expect(actions).toHaveCount(1);
  await expect(actions).toHaveText('Log in');
  await actions.click();
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  const form = page.getByTestId('auth-modal');
  await form.getByLabel('Work email').fill(user.email);
  await form.getByLabel('Password', { exact: true }).fill('test-only-password');
  await form.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/#dashboard\//);
});

/** A browser with no WebGL at all, as on some old or locked-down machines. */
const NO_WEBGL = () => {
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...args) {
    return /webgl/.test(type) ? null : getContext.call(this, type, ...args);
  };
};

test('without WebGL the recorded mascot plays and follows the page', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(NO_WEBGL);
  const models = [];
  page.on('request', (request) => { if (request.url().includes('.glb')) models.push(request.url()); });
  await openHome(page, '/', { render: null });
  const bot = page.getByTestId('scroll-bot');
  await expect(bot).toHaveAttribute('data-render', 'video');
  const video = bot.locator('.mk-bot-video');
  // The hero's wave plays as video, really playing, with no 3D anywhere.
  await expect(video).toHaveAttribute('data-clip', 'RIGHT_HAND_WAVE', { timeout: 15000 });
  await expect.poll(() => video.locator('video').evaluateAll((list) => list.some((v) => !v.paused && v.readyState >= 2))).toBe(true);
  await expect(bot.locator('canvas')).toHaveCount(0);
  await expect(page.getByText(/3D could not load|Restoring 3D/)).toHaveCount(0);

  // "How it works": it reaches out to the steps, then listens, as the live one does.
  const clips = [];
  await page.exposeFunction('__recordClip', (clip) => clips.push(clip));
  await video.evaluate((el) => new MutationObserver(() => window.__recordClip(el.dataset.clip))
    .observe(el, { attributes: true, attributeFilter: ['data-clip'] }));
  await scrollToTop(page, '#how-it-works');
  await expect.poll(() => clips.join(','), { timeout: 10000 }).toContain('REACH_RIGHT,LISTENING');
  // Tapping it still gets a reaction.
  await bot.locator('.mk-bot-hit').click({ position: { x: 120, y: 30 } });
  await expect(bot).toHaveAttribute('data-bot-tap', 'Hey, that tickles.');
  await expect(video).toHaveAttribute('data-clip', 'NOD');
  expect(models).toEqual([]);
});

test('without WebGL the sign-in page plays its recorded effects', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(NO_WEBGL);
  await openHome(page, '/signin', { render: null });
  const signin = page.getByTestId('signin-page');
  await expect(signin.locator('canvas')).toHaveCount(0);
  const playing = (selector) => signin.locator(selector).evaluate((v) => !v.paused && v.readyState >= 2);
  await expect.poll(() => playing('.signin-bg-video')).toBe(true);
  await expect.poll(() => playing('.signin-laser-video')).toBe(true);
  // The recorded beam lands on the card's top-right corner: 560px in and 240px down.
  const card = await signin.locator('.signin-card').boundingBox();
  const beam = await signin.locator('.signin-laser-video').boundingBox();
  expect(Math.abs(beam.x + 560 - (card.x + card.width))).toBeLessThan(2);
  expect(Math.abs(beam.y + 240 - card.y)).toBeLessThan(2);
  await expect(page.getByTestId('auth-modal')).toBeVisible();
});
