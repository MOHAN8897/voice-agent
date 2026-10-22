import { test, expect } from '@playwright/test';

test.use({
  launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'] },
  permissions: ['microphone'],
});

async function installMediaHarness(page) {
  await page.goto('/');
  await page.evaluate(async () => {
    const { api } = await import('/src/services/api.js');
    const { createWebAgentSession } = await import('/src/services/webAgentClient.js');
    api.setToken('browser-startup-test-token');
    window.__audioStarts = 0;
    window.__audioStops = 0;
    window.__micBytes = 0;
    window.__ready = false;
    window.__events = [];
    const originalStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (...args) {
      window.__audioStarts += 1;
      return originalStart.apply(this, args);
    };
    const originalStop = AudioBufferSourceNode.prototype.stop;
    AudioBufferSourceNode.prototype.stop = function (...args) {
      window.__audioStops += 1;
      return originalStop.apply(this, args);
    };
    const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const stream = await capture(constraints);
      window.__micStream = stream;
      return new Promise((resolve) => { window.__releaseMic = () => resolve(stream); });
    };
    class MediaSocket {
      static OPEN = 1;
      constructor(url, protocols) {
        window.__socket = this;
        this.url = String(url);
        this.protocols = protocols;
        this.readyState = 0;
        this.bufferedAmount = 0;
        setTimeout(() => {
          if (this.readyState === 3) return;
          this.readyState = 1;
          this.reply();
          this.onmessage?.({ data: JSON.stringify({ type: 'ready', callId: 'media-startup-check', sampleRate: 16000 }) });
        }, 30);
      }
      reply() {
        const pcm = new Int16Array(320);
        for (let i = 0; i < pcm.length; i += 1) pcm[i] = Math.sin(i / 8) * 2000;
        this.onmessage?.({ data: pcm.buffer });
      }
      send(data) { if (data instanceof ArrayBuffer) window.__micBytes += data.byteLength; }
      close() { this.readyState = 3; this.onclose?.(); }
    }
    window.WebSocket = MediaSocket;
    window.__session = createWebAgentSession();
    window.__session.subscribe((event, data) => {
      window.__events.push(event);
      if (event === 'ready') { window.__ready = true; window.__microphoneMode = data.microphoneMode; }
    });
    window.__starting = window.__session.start({ agentId: 'test-agent', language: 'te-IN' }).then(
      () => 'started', (error) => error.message
    );
  });
}

test('plays greeting before delayed mic permission, then captures mic and plays the next reply', async ({ page }) => {
  await installMediaHarness(page);
  await expect.poll(() => page.evaluate(() => window.__audioStarts)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__ready)).toBe(false);
  await expect.poll(() => page.evaluate(() => Boolean(window.__releaseMic))).toBe(true);
  await page.evaluate(() => window.__releaseMic());
  expect(await page.evaluate(() => window.__starting)).toBe('started');
  await expect.poll(() => page.evaluate(() => window.__micBytes)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__microphoneMode)).toBe('capturing');
  const before = await page.evaluate(() => window.__audioStarts);
  await page.evaluate(() => window.__socket.reply());
  await expect.poll(() => page.evaluate(() => window.__audioStarts)).toBeGreaterThan(before);
  await page.evaluate(() => {
    for (let i = 0; i < 20; i += 1) window.__socket.reply();
    window.__socket.onmessage({ data: JSON.stringify({ type: 'clear_audio' }) });
  });
  expect(await page.evaluate(() => window.__audioStops)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__events.includes('interrupted'))).toBe(true);
  await page.evaluate(() => window.__session.stop());
  expect(await page.evaluate(() => window.__micStream.getTracks().every((track) => track.readyState === 'ended'))).toBe(true);
});

test('stop cancels startup and releases a microphone granted after cancellation', async ({ page }) => {
  await installMediaHarness(page);
  await expect.poll(() => page.evaluate(() => Boolean(window.__releaseMic))).toBe(true);
  await page.evaluate(() => window.__session.stop());
  await page.evaluate(() => window.__releaseMic());
  expect(await page.evaluate(() => window.__starting)).toMatch(/stopped/);
  await expect.poll(() => page.evaluate(() => window.__micStream.getTracks().every((track) => track.readyState === 'ended'))).toBe(true);
  expect(await page.evaluate(() => window.__ready)).toBe(false);
  expect(await page.evaluate(() => window.__socket.readyState)).toBe(3);
});
