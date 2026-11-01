#!/usr/bin/env node
/**
 * Records the sign-in page's WebGL effects (Ghost Fibers, Laser Flow) as PNG frames for
 * devices that cannot run them live. The page's requestAnimationFrame and performance.now
 * are replaced by a clock this script steps, one frame per call, 1/30s apart, however
 * slow the machine. A `crossfade` effect records a second past its loop length;
 * encode_effects.py fades that tail into the start so the video loops without a seam.
 *
 * The fibers are recorded on /signin itself with everything but the background hidden;
 * the laser on scripts/capture/effects.html, against an invisible stand-in card.
 *
 *   npm run dev
 *   node scripts/capture/capture-effects.mjs <out-dir> [base-url]
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const FPS = 30;
const FADE_S = 1;
/**
 * Seconds looped, when recording starts (after the opening animation, in the steady
 * drift a visitor mostly sees), the page, the region kept, and the viewport.
 */
export const EFFECTS = {
  fibers: {
    loop: 8, start: 6, mode: 'crossfade', url: '/signin', hide: '.signin > :not(.signin-bg) { visibility: hidden !important; }',
    viewport: { width: 1280, height: 800 }, clip: { x: 0, y: 0, width: 1280, height: 800 },
  },
  // The beam lands on the card's top-right corner at (672, 240); keep 560px left of it
  // (the light running along the card's top edge), the 192px to the layer's edge, and the
  // layer's full height, so the glow beside the card never ends in a hard line.
  laser: {
    loop: 6, start: 2, mode: 'crossfade', url: '/scripts/capture/effects.html',
    viewport: { width: 864, height: 820 }, clip: { x: 112, y: 0, width: 752, height: 820 },
  },
};

/** A frame clock the script advances by hand. */
const MANUAL_CLOCK = () => {
  let now = 0;
  let queue = new Map();
  let id = 0;
  performance.now = () => now;
  window.requestAnimationFrame = (callback) => { id += 1; queue.set(id, callback); return id; };
  window.cancelAnimationFrame = (handle) => queue.delete(handle);
  window.__advance = (ms) => {
    now += ms;
    const due = queue;
    queue = new Map();
    due.forEach((callback) => callback(now));
  };
};

const [outDir, baseUrl = 'http://127.0.0.1:5173'] = process.argv.slice(2);
if (!outDir) {
  console.error('usage: capture-effects.mjs <out-dir> [base-url]');
  process.exit(1);
}

const browser = await chromium.launch({ channel: 'chrome', args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
for (const [name, effect] of Object.entries(EFFECTS)) {
  const page = await browser.newPage({ viewport: effect.viewport, deviceScaleFactor: 1 });
  page.on('pageerror', (error) => console.error(`${name}: page error:`, error.message));
  await page.addInitScript(MANUAL_CLOCK);
  await page.route('**/api/**', (route) => route.fulfill({ json: { authenticated: false } }));
  await page.goto(`${baseUrl}${effect.url}`);
  await page.waitForSelector('canvas');
  if (effect.hide) await page.addStyleTag({ content: effect.hide });
  // One frame per call, so the browser lays out, observes and composites between frames
  // just as it does live.
  const step = () => page.evaluate((ms) => window.__advance(ms), 1000 / FPS);
  for (let i = 0; i < effect.start * FPS; i += 1) await step();

  const dir = path.join(outDir, name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const frames = Math.round((effect.loop + (effect.mode === 'crossfade' ? FADE_S : 0)) * FPS);
  for (let i = 0; i < frames; i += 1) {
    await step();
    await page.screenshot({ path: path.join(dir, `f${String(i).padStart(4, '0')}.png`), clip: effect.clip });
  }
  fs.writeFileSync(path.join(dir, 'effect.json'), JSON.stringify({ fps: FPS, mode: effect.mode, loopFrames: effect.loop * FPS, fadeFrames: FADE_S * FPS }));
  console.log(`${name}: ${frames} frames`);
  await page.close();
}
await browser.close();
