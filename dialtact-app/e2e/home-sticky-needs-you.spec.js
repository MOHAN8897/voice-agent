import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.
// The Home feed's sticky "Needs you" header must sit under the sticky Activity
// filter bar on a solid background and never cover a row's text.

const SHOTS = process.env.STICKY_SHOTS_DIR || 'test-results/home-sticky';
const AGENT = 'voice-setup-agent';
const iso = (minutesAgo) => new Date(Date.now() - minutesAgo * 60_000).toISOString();

const pinned = ['+919398247132', '+919000000011', '+919000000012'].map((phone, i) => ({
  id: `followup:pin-${i}`, type: 'followup.review', category: 'calls', at: iso(5 + i), tone: 'warning',
  actor: null, text: `A callback to ${phone.replace(/^\+91(\d{5})(\d{5})$/, '+91 $1 $2')} needs your approval`,
  detail: 'Asked for: tomorrow evening', agentId: AGENT, contact: { phone }, needsAction: true,
  actions: [{ kind: 'open_followups', label: 'Review' }], refs: {}, meta: {},
}));
const items = Array.from({ length: 24 }, (_, i) => ({
  id: `call:${i}`, type: 'call.completed', category: 'calls', at: iso(30 + i * 20), tone: 'neutral',
  actor: 'Hima', text: `Hima finished a call with +91 90000 ${String(10000 + i)}`, detail: 'Asked about prices and timings',
  agentId: AGENT, contact: { phone: `+9190000${10000 + i}` }, needsAction: false, actions: [], refs: {}, meta: {},
}));

async function openHome(page) {
  await setupVoiceWorkspace(page);
  await page.route('**/api/activity/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/feed')) return route.fulfill({ json: { items, pinned, needsActionCount: pinned.length, nextCursor: null } });
    return route.fulfill({ json: { calls: [], counts: {}, items: [] } });
  });
  await page.goto('/#dashboard/overview');
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  await expect(page.getByTestId('home-pinned')).toBeVisible();
}

// Geometry of the stuck headers and the rows around them, read in one go.
async function measure(page) {
  return page.evaluate(() => {
    const bar = document.querySelector('[data-testid="home-feed-header"]').getBoundingClientRect();
    const head = document.querySelector('[data-testid="home-needs-you-header"]');
    const box = head.getBoundingClientRect();
    const bg = getComputedStyle(head).backgroundColor;
    // The row text visible directly under the header's bottom edge.
    const rows = [...document.querySelectorAll('[data-testid="home-pinned"] [data-item-id]')].map((r) => r.getBoundingClientRect());
    return { barBottom: bar.bottom, headTop: box.top, headBottom: box.bottom, bg, rows: rows.map((r) => ({ top: r.top, bottom: r.bottom })) };
  });
}

function alpha(color) {
  const m = color.match(/rgba?\(([^)]+)\)/) || color.match(/color\(srgb ([^)]+)\)/);
  if (!m) return 1;
  const parts = m[1].split(/[ ,/]+/).filter(Boolean);
  return parts.length === 4 ? Number(parts[3]) : 1;
}

for (const [label, size] of [['desktop', { width: 1366, height: 768 }], ['mobile', { width: 390, height: 844 }]]) {
  test(`Needs you header stays under the Activity bar without covering rows (${label})`, async ({ page }) => {
    await page.setViewportSize(size);
    await openHome(page);
    const header = page.getByTestId('home-needs-you-header');
    await expect(header).toContainText('Needs you');

    // At rest: the header sits above the first row, not on it.
    let m = await measure(page);
    expect(m.headBottom).toBeLessThanOrEqual(m.rows[0].top + 0.5);
    await page.screenshot({ path: `${SHOTS}/${label}-rest.png` });

    // Scroll the console's <main> until the Activity bar is stuck and the first
    // pinned row has slid under the "Needs you" header.
    await page.evaluate(() => {
      const main = document.querySelector('main');
      const pin = document.querySelector('[data-testid="home-pinned"]');
      main.scrollTop += pin.getBoundingClientRect().top - main.getBoundingClientRect().top + 30;
    });
    await expect(page.getByTestId('home-feed-header')).toHaveAttribute('data-stuck', 'true');
    m = await measure(page);
    // Directly under the filter bar: no gap, no overlap.
    expect(Math.abs(m.headTop - m.barBottom)).toBeLessThanOrEqual(1);
    // Solid: nothing under it shows through.
    expect(alpha(m.bg)).toBe(1);
    await expect(header).toHaveAttribute('data-stuck', 'true');
    await page.screenshot({ path: `${SHOTS}/${label}-scrolled.png` });

    // Nothing scrolls sideways on a phone.
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  });
}
