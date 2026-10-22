import { test, expect } from '@playwright/test';

test('browser voice client accepts readiness and plays server audio', async ({ page }) => {
  let webAgentSocket;
  let webAgentSocketUrl;
  const browserAudioMessages = [];
  await page.routeWebSocket(/\/ws\/web-agent(?:\?|$)/, (socket) => {
    webAgentSocket = socket;
    webAgentSocketUrl = socket.url();
    socket.onMessage((message) => browserAudioMessages.push(message));
    socket.send(JSON.stringify({
      type: 'ready',
      callId: 'playwright-call',
      sampleRate: 16000,
      voiceProvider: 'openai',
      voiceModel: 'playwright-model',
    }));
  });

  await page.addInitScript(() => {
    const permissions = navigator.permissions;
    let permissionQueried = false;
    Object.defineProperty(permissions, 'query', {
      configurable: true,
      value: async ({ name }) => {
        permissionQueried = true;
        return { state: name === 'microphone' ? 'denied' : 'granted' };
      },
    });
    window.__audioTrace = [];
    class TestAudioContext {
      constructor(options = {}) {
        this.state = 'suspended';
        this.sampleRate = options.sampleRate || 48000;
        this.currentTime = 0;
        this.destination = {};
        window.__audioTrace.push({ type: 'created', beforePermissionQuery: !permissionQueried });
      }
      resume() {
        this.state = 'running';
        window.__audioTrace.push({ type: 'resumed' });
        return Promise.resolve();
      }
      createBuffer(_channels, length, sampleRate) {
        const channel = new Float32Array(length);
        return { duration: length / sampleRate, getChannelData: () => channel };
      }
      createBufferSource() {
        return {
          buffer: null,
          connect() {},
          start: (when) => window.__audioTrace.push({ type: 'played', when, state: this.state }),
        };
      }
      close() {
        this.state = 'closed';
        return Promise.resolve();
      }
    }
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: TestAudioContext });
  });
  await page.goto('/');

  const events = await page.evaluate(async () => {
    sessionStorage.setItem('voxly_auth_token', 'playwright-test-token');
    const { createWebAgentSession } = await import('/src/services/webAgentClient.js');
    const session = createWebAgentSession();
    const received = [];
    session.subscribe((event) => received.push(event));
    await session.start({ agentId: 'playwright-agent', language: 'en-IN' });
    window.__webAgentSession = session;
    window.__webAgentSessionEvents = received;
    return received;
  });

  expect(events).toContain('ready');
  expect(new URL(webAgentSocketUrl).searchParams.has('token')).toBe(false);
  expect(new URL(webAgentSocketUrl).searchParams.get('language')).toBe('en-IN');
  webAgentSocket.send(Buffer.from([0, 0, 0, 0, 0, 0, 0, 0]));
  await expect.poll(() => page.evaluate(() => window.__webAgentSessionEvents)).toContain('audio');
  await expect.poll(() => page.evaluate(() => window.__audioTrace.some((entry) => entry.type === 'played'))).toBe(true);
  expect(await page.evaluate(() => window.__audioTrace)).toEqual(expect.arrayContaining([
    expect.objectContaining({ type: 'created', beforePermissionQuery: true }),
    expect.objectContaining({ type: 'played', state: 'running' }),
  ]));
  await page.evaluate(() => window.__webAgentSession.stop());
});

test('browser voice client sends captured microphone PCM to the server', async ({ page }) => {
  const browserAudioMessages = [];
  let webAgentSocket;
  await page.routeWebSocket(/\/ws\/web-agent(?:\?|$)/, (socket) => {
    webAgentSocket = socket;
    socket.onMessage((message) => browserAudioMessages.push(message));
    socket.send(JSON.stringify({ type: 'ready', callId: 'playwright-mic-call', sampleRate: 16000 }));
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator.permissions, 'query', {
      configurable: true,
      value: async () => ({ state: 'granted' }),
    });
    const track = { stop() {} };
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: async () => ({ getTracks: () => [track] }) },
    });
    window.__capturedProcessor = null;
    class TestAudioContext {
      constructor(options = {}) {
        this.state = 'suspended';
        this.sampleRate = options.sampleRate || 48000;
        this.currentTime = 0;
        this.destination = {};
      }
      resume() { this.state = 'running'; return Promise.resolve(); }
      close() { this.state = 'closed'; return Promise.resolve(); }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createScriptProcessor() {
        const processor = { connect() {}, disconnect() {}, onaudioprocess: null };
        window.__capturedProcessor = processor;
        return processor;
      }
      createGain() { return { gain: { value: 1 }, connect() {}, disconnect() {} }; }
    }
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: TestAudioContext });
  });
  await page.goto('/');
  await page.evaluate(async () => {
    sessionStorage.setItem('voxly_auth_token', 'playwright-test-token');
    const { createWebAgentSession } = await import('/src/services/webAgentClient.js');
    const session = createWebAgentSession();
    await session.start({ agentId: 'playwright-agent', language: 'hi-IN' });
    window.__webAgentSession = session;
  });
  await page.evaluate(() => {
    window.__capturedProcessor.onaudioprocess({
      inputBuffer: { getChannelData: () => new Float32Array([0.25, -0.25, 0.5, -0.5]) },
    });
  });
  await expect.poll(() => browserAudioMessages.some((message) => message instanceof ArrayBuffer || Buffer.isBuffer(message))).toBe(true);
  await page.evaluate(() => window.__webAgentSession.stop());
});
