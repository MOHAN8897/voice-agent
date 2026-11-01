#!/usr/bin/env node
/**
 * Renders every move the home page's mascot makes into PNG frames with a transparent
 * background, by stepping the real 3D mascot (scripts/capture/mascot.html) one frame at
 * a time. encode-mascot.mjs then turns each folder into a video.
 *
 *   npm run dev                                   (the capture page is served by Vite)
 *   node scripts/capture/capture-mascot.mjs <out-dir> [base-url] [clip,clip,…]
 *
 * Loops (the moods the mascot settles into) are exactly one period of their clip, so they
 * repeat seamlessly. Gestures start from rest and include the blend back to rest. The
 * gentle float is left out (reduced motion): the page adds it, so it never jumps when
 * one clip hands over to the next.
 */
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const FPS = 30;
const SETTLE_S = 1.5;
const BLEND_BACK_S = 0.35;

/** Moods: looped while the mascot stands in a section (data-bot-state, taps, the demo). */
export const LOOPS = ['IDLE', 'HAPPY', 'CONFIDENT', 'LISTENING', 'CURIOUS', 'THINKING', 'EXCITED', 'SURPRISED', 'TALKING'];
/** One-shot gestures the page asks for (data-bot-gesture, taps, hover). */
export const GESTURES = {
  RIGHT_HAND_WAVE: 'HAPPY', LEFT_HAND_WAVE: 'HAPPY', DOUBLE_WAVE: 'EXCITED', CELEBRATE: 'EXCITED',
  STRETCH: 'HAPPY', EXPLAIN: 'CONFIDENT', SCAN: 'CURIOUS', NOD: 'CONFIDENT', HOP: 'EXCITED',
  PRESENT: 'HAPPY', PRESENT_RIGHT: 'HAPPY', REACH_LEFT: 'CONFIDENT', REACH_RIGHT: 'CONFIDENT',
};

/** A periodic "speech" envelope for the talking loop, so its mouth loops cleanly too. */
const speech = (phase) => 0.12 + 0.62 * Math.abs(Math.sin(2 * Math.PI * 5 * phase)) * (0.65 + 0.35 * Math.sin(2 * Math.PI * 2 * phase));

const [outDir, baseUrl = 'http://127.0.0.1:5173', only] = process.argv.slice(2);
if (!outDir) {
  console.error('usage: capture-mascot.mjs <out-dir> [base-url] [clip,clip,…]');
  process.exit(1);
}
const wanted = only ? new Set(only.split(',')) : null;

const browser = await chromium.launch({ channel: 'chrome', args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 800, height: 600 }, reducedMotion: 'reduce' });
page.on('pageerror', (error) => console.error('page error:', error.message));
await page.goto(`${baseUrl}/scripts/capture/mascot.html`);
await page.waitForFunction(() => window.__bot && window.__frame && window.__clips, null, { timeout: 60000 });
const clips = await page.evaluate(() => window.__clips);

let t = 0;
const step = async (frames, amplitude) => {
  for (let i = 0; i < frames; i += 1) {
    t += 1 / FPS;
    await page.evaluate(([time, amp]) => {
      if (amp !== null) window.__bot.setAudioAmplitude(amp);
      window.__step(time);
    }, [t, amplitude ? amplitude(i) : null]);
  }
};
const record = async (dir, frames, amplitude) => {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  for (let i = 0; i < frames; i += 1) {
    t += 1 / FPS;
    const url = await page.evaluate(([time, amp]) => {
      if (amp !== null) window.__bot.setAudioAmplitude(amp);
      return window.__frame(time);
    }, [t, amplitude ? amplitude(i) : null]);
    fs.writeFileSync(path.join(dir, `f${String(i).padStart(4, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
  }
};

const manifest = { fps: FPS, width: 950, height: 706, clips: {} };
const manifestPath = path.join(outDir, 'manifest.json');
if (fs.existsSync(manifestPath)) Object.assign(manifest.clips, JSON.parse(fs.readFileSync(manifestPath, 'utf8')).clips);

for (const mood of LOOPS) {
  if (wanted && !wanted.has(mood)) continue;
  const clip = clips[mood] ? mood : 'IDLE';
  const frames = Math.round(clips[clip] * FPS);
  const talking = mood === 'TALKING';
  const amplitude = talking ? (i) => speech((i % frames) / frames) : null;
  await page.evaluate((name) => {
    window.__bot.setAudioAmplitude(0);
    window.__bot.setState(name);
  }, mood);
  // Settle a whole number of periods, so the talking envelope is in phase when recording starts.
  await step(Math.ceil((SETTLE_S * FPS) / frames) * frames, amplitude);
  await record(path.join(outDir, mood), frames, amplitude);
  manifest.clips[mood] = { loop: true, frames };
  console.log(`${mood}: ${frames} frames (loop of ${clip})`);
}

for (const [move, face] of Object.entries(GESTURES)) {
  if (wanted && !wanted.has(move)) continue;
  if (!clips[move]) { console.warn(`${move}: no clip in the model, skipped`); continue; }
  await page.evaluate((expression) => {
    window.__bot.setAudioAmplitude(0);
    window.__bot.setState('IDLE');
    window.__bot.setExpression(expression);
  }, face);
  await step(Math.round(SETTLE_S * FPS));
  await page.evaluate((name) => window.__bot.setState(name), move);
  const frames = Math.round((clips[move] + BLEND_BACK_S) * FPS);
  await record(path.join(outDir, move), frames);
  manifest.clips[move] = { loop: false, frames };
  console.log(`${move}: ${frames} frames`);
}

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
await browser.close();
