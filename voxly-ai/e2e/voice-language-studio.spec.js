import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const testAgent = {
  id: 'voice-playwright-agent',
  name: 'Playwright voice test agent',
  status: 'active',
  language: 'te-IN',
  languages: ['te-IN'],
  sections: [],
};
let voiceStackPatchBody = null;
let persistedTestAgent = null;

test.describe('Voice and Language Configuration in Agent Console', () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    voiceStackPatchBody = null;
    persistedTestAgent = { ...testAgent };
    page.on('pageerror', (err) => {
      console.log('BROWSER PAGE ERROR:', err.message);
      consoleErrors.push(err.message);
    });
    // This suite uses a synthetic tenant; never send its token to the real API.
    await page.route('**/api/**', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: '{}',
    }));

    // Use an isolated UI session and mock reads/writes so this flow does not
    // depend on an expiring local account or spend live voice credits.
    const base64url = (value) => Buffer.from(value).toString('base64url');
    const token = `${base64url(JSON.stringify({ alg: 'none', typ: 'JWT' }))}.${base64url(
      JSON.stringify({ sub: 'voice-playwright-user', exp: Math.floor(Date.now() / 1000) + 3600 })
    )}.test`;
    const sessionUser = {
      id: 'voice-playwright-user',
      name: 'Playwright Voice Tester',
      email: 'voice-test@example.invalid',
      tenantId: 'voice-playwright-tenant',
      role: 'subscriber',
      hasCompletedOnboarding: true,
    };
    await page.route('**/api/auth/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { userId: sessionUser.id, email: sessionUser.email, hasCompletedOnboarding: true },
          tenant: { tenantId: sessionUser.tenantId },
          role: sessionUser.role,
        }),
      })
    );
    await page.route('**/api/agents', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agents: [persistedTestAgent] }) })
    );
    const previewSample = path.resolve(__dirname, '../public/audio/voxly/samples/marin.wav');
    await page.route('**/api/telephony/voice-preview*', (route) =>
      route.fulfill({ status: 200, contentType: 'audio/wav', body: fs.readFileSync(previewSample) })
    );
    await page.route('**/api/telephony/voice-options*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          stackLabel: 'Gemini Live',
          activeVoiceProvider: 'gemini',
          activeModel: 'gemini-3.8-live',
          defaultVoiceId: 'te-in-csagent-5',
          voices: [
            { id: 'puck', label: 'Puck', provider: 'gemini', geminiVoice: 'Puck', category: 'sales', gender: 'male' },
            { id: 'te-in-csagent-1', label: 'Telugu Support · Female 1', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'female', sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-csagent-4', label: 'Telugu Support · Male', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'male', sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-csagent-5', label: 'Telugu Support · Female', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'female', defaultForLanguage: true, sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-csagent-7', label: 'Telugu Support · Neutral', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'neutral', sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-concierge-2', label: 'Telugu Concierge · Male', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'male', sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-concierge-7', label: 'Telugu Concierge · Female', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'support', gender: 'female', sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
            { id: 'te-in-techagent-1', label: 'Telugu Tech Support · Female', provider: 'gemini', languageCode: 'te-IN', accent: 'Telugu (India)', category: 'operations', gender: 'female', sampleText: 'నమస్కారం. మీ సాంకేతిక సమస్యకు సహాయం చేస్తాను.' },
          ],
          languages: [{ code: 'te-IN', label: 'Telugu' }],
        }),
      })
    );
    await page.route('**/api/billing/wallet', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ balanceUsd: 100, balanceInr: 0, fxRateInr: 94 }),
      })
    );
    await page.route('**/api/voice-stacks/catalog*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          profiles: [
            {
              tier: 'low',
              label: 'Economical Tier',
              ready: true,
              profileRevision: 2,
              retailRate: { amount: 0.7, currency: 'INR' },
              engines: [
                {
                  id: 'turbo-natural',
                  label: 'Turbo Natural Engine',
                  models: [{
                    id: 'turbo-regional',
                    label: 'Turbo Regional',
                    voices: [{ id: 'voice-economical-te', label: 'Telugu Assistant', languages: ['te-IN'] }],
                  }],
                },
              ],
            },
            {
              tier: 'medium',
              label: 'Standard Regional Tier',
              ready: true,
              profileRevision: 5,
              retailRate: { amount: 1.4, currency: 'INR' },
              engines: [
                {
                  id: 'regional-expressive',
                  label: 'Regional Expressive Engine',
                  models: [{
                    id: 'regional-fast',
                    label: 'Regional Fast',
                    voices: [{ id: 'voice-regional-te', label: 'Telugu Support', languages: ['te-IN'] }],
                  }],
                },
                {
                  id: 'turbo-natural',
                  label: 'Turbo Natural Engine',
                  models: [{
                    id: 'turbo-standard',
                    label: 'Turbo Standard',
                    voices: [{ id: 'voice-standard-te', label: 'Telugu Assistant', languages: ['te-IN'] }],
                  }],
                },
              ],
            },
            {
              tier: 'premium',
              label: 'Internal Live Provider',
              ready: true,
              profileRevision: 8,
              retailRate: { amount: 4.2, currency: 'INR' },
              engines: [],
            },
          ],
        }),
      })
    );
    await page.route('**/api/agents/**', async (route) => {
      const method = route.request().method().toUpperCase();
      const pathname = new URL(route.request().url()).pathname;
      if (method === 'GET') {
        const data = pathname.endsWith('/telephony-profile')
          ? { profile: {}, afterHoursActions: [] }
          : pathname.endsWith('/telephony-profile/effective')
            ? { ok: true }
            : { ok: true, agent: persistedTestAgent, sections: [] };
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
        return;
      }
      if (method === 'PATCH') {
        const body = route.request().postDataJSON();
        if (body?.voiceSettings?.stackSelectionVersion === 1) {
          voiceStackPatchBody = body;
          persistedTestAgent = {
            ...persistedTestAgent,
            defaultTier: body.defaultTier,
            voiceSettings: body.voiceSettings,
            voiceRevision: body.expectedVoiceRevision + 1,
          };
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              ok: true,
              agent: {
                ...persistedTestAgent,
              },
            }),
          });
          return;
        }
      }
      const agentId = route.request().url().match(/\/api\/agents\/([^/?]+)/)?.[1] || 'playwright-agent';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          agent: { id: agentId, name: 'Playwright voice test agent', status: 'active', languages: ['te-IN'] },
        }),
      });
    });

    await page.addInitScript(
      ({ accessToken, sessionUser }) => {
        sessionStorage.setItem('voxly_auth_token', accessToken);
        sessionStorage.setItem('dialtact_auth_token', accessToken);
        localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
        localStorage.setItem('dialtact_auth_session', JSON.stringify(sessionUser));
        localStorage.setItem('voxly_tour_completed', 'true');
        localStorage.setItem('voxly_tour_completed_default', 'true');
        localStorage.setItem('voxly_tour_completed_voice-test@example.invalid', 'true');
        localStorage.setItem('dialtact_tour_completed_default', 'true');

        const style = document.createElement('style');
        style.innerHTML = '.driver-overlay, .driver-popover { display: none !important; pointer-events: none !important; }';
        const installTourStyle = () => {
          const root = document.head || document.documentElement;
          if (root) root.appendChild(style);
        };
        if (document.head || document.documentElement) installTourStyle();
        else document.addEventListener('DOMContentLoaded', installTourStyle, { once: true });
      },
      { accessToken: token, sessionUser }
    );
  });

  test('Voice and Language studio renders cards, plays preconfigured sample playback, and changes voice/language', async ({
    page,
  }, testInfo) => {
    // 1. Navigate to overview first to ensure session bootstrap
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);

    // Close any driver tour if somehow still mounted
    await page.evaluate(() => {
      document.querySelectorAll('.driver-overlay, .driver-popover').forEach((el) => el.remove());
    });

    // 2. Navigate directly to the mocked employee workbench.
    const targetAgentId = testAgent.id;
    await page.goto(`/#dashboard/employees?step=overview&agent=${targetAgentId}`);
    await page.waitForTimeout(2000);

    // If not in studio yet, fallback to clicking agent card
    const voiceTabCheck = page.locator('#agent-tab-voice');
    if (!(await voiceTabCheck.isVisible())) {
      await page.goto('/#dashboard/employees');
      await page.waitForTimeout(1500);
      const agentCard = page.locator('[data-testid="agent-card"]').first();
      await agentCard.click({ force: true });
      await page.waitForTimeout(2000);
    }

    // 4. Click the Voice tab
    console.log('Navigating to Voice tab...');
    const voiceTab = page.locator('#agent-tab-voice');
    await expect(voiceTab).toBeVisible({ timeout: 15000 });
    await voiceTab.click();
    await page.waitForTimeout(1500);

    // 5. Verify Voice & Language Studio container mounted
    const voicePanel = page.locator('[data-testid="agent-voice-panel"]');
    await expect(voicePanel).toBeVisible({ timeout: 10000 });

    // Verify key sections are present
    await expect(page.locator('[data-testid="language-selection-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="speaking-voice-showcase"]')).toBeVisible();
    await expect(page.locator('[data-testid="acoustic-calibration-card"]')).toBeVisible();
    await expect(page.locator('[data-testid="greeting-preview-card"]')).toBeVisible();

    // 6. Test Language Selection: Select Telugu (te-IN)
    console.log('Testing Telugu (te-IN) language card selection...');
    const teluguCard = page.locator('[data-testid="language-card-te-IN"]');
    await expect(teluguCard).toBeVisible();
    await teluguCard.click();
    await page.waitForTimeout(600);

    // Verify Telugu is now active
    await expect(teluguCard).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-testid="language-selection-card"]')).toContainText(/Active: Telugu \(te-IN\)/i);
    const defaultTeluguVoice = page.locator('[data-testid="voice-card-te-in-csagent-5"]');
    await expect(defaultTeluguVoice).toBeVisible();
    await expect(defaultTeluguVoice).toContainText(/Selected/i);

    const voiceOptions = await page.evaluate(async () => {
      const { fetchPhoneVoiceOptions } = await import('/src/lib/voiceStack.js');
      return fetchPhoneVoiceOptions('te-IN');
    });
    const activeVoiceProvider = voiceOptions.activeVoiceProvider;
    expect(activeVoiceProvider).toBe('gemini');
    expect(voiceOptions.defaultVoiceId).toBe('te-in-csagent-5');
    const visibleVoiceRows = voiceOptions.voices.filter(
      (voice) => voice.provider === activeVoiceProvider && (!voice.languageCode || voice.languageCode === 'te-IN')
    );
    expect(visibleVoiceRows.length).toBeGreaterThanOrEqual(5);

    // 7. Test Voice Filtering and category counts
    console.log('Testing voice filtering by category...');
    const careFilter = page.locator('[data-testid="voice-filter-care"]');
    await careFilter.click();
    await page.waitForTimeout(400);
    expect(await page.locator('[data-testid^="voice-card-"]').count()).toBe(
      visibleVoiceRows.filter((voice) => ['support', 'care'].includes(voice.category)).length
    );

    const formalFilter = page.locator('[data-testid="voice-filter-formal"]');
    await formalFilter.click();
    await page.waitForTimeout(400);
    expect(await page.locator('[data-testid^="voice-card-"]').count()).toBe(
      visibleVoiceRows.filter((voice) => ['operations', 'formal'].includes(voice.category)).length
    );

    const salesFilter = page.locator('[data-testid="voice-filter-energetic"]');
    await salesFilter.click();
    await page.waitForTimeout(400);
    expect(await page.locator('[data-testid^="voice-card-"]').count()).toBe(
      visibleVoiceRows.filter((voice) => ['sales', 'energetic'].includes(voice.category)).length
    );

    // All Filter
    const allFilter = page.locator('[data-testid="voice-filter-all"]');
    await allFilter.click();
    await page.waitForTimeout(400);
    expect(await page.locator('[data-testid^="voice-card-"]').count()).toBe(visibleVoiceRows.length);

    // 8. Verify voice playback through the selected provider.
    const previewVoice = visibleVoiceRows[0];
    expect(previewVoice).toBeTruthy();
    const previewCard = page.locator(`[data-testid="voice-card-${previewVoice.id}"]`);
    await expect(previewCard).toBeVisible();
    const playBtn = page.locator(`[data-testid="voice-play-btn-${previewVoice.id}"]`);
    await expect(playBtn).toBeVisible();
    let previewRequest = null;
    if (activeVoiceProvider === 'gemini') {
      const samplePath = path.resolve(__dirname, '../public/audio/voxly/samples/marin.wav');
      await page.route('**/api/telephony/voice-preview*', async (route) => {
        previewRequest = route.request().postDataJSON();
        await route.fulfill({ status: 200, contentType: 'audio/wav', body: fs.readFileSync(samplePath) });
      });
    }
    await playBtn.click();
    await page.waitForTimeout(800);

    // Check that playing indicator is active
    const playingIndicator = page.locator('[data-testid="voice-playing-indicator"]');
    await expect(playingIndicator).toBeVisible({ timeout: 8000 });
    await expect(playingIndicator).toContainText(/Playing/i);
    await expect(playingIndicator).toContainText(new RegExp(previewVoice.label || previewVoice.name || previewVoice.id, 'i'));
    if (activeVoiceProvider === 'gemini') {
      await expect.poll(() => previewRequest).toMatchObject({ voiceId: previewVoice.id, language: 'te-IN' });
    }

    // Stop playback
    const stopBtn = page.locator('[data-testid="stop-voice-audio-btn"]');
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await page.waitForTimeout(500);
      await expect(playingIndicator).toHaveCount(0);
    }

    if (activeVoiceProvider === 'gemini') {
      const accessMessage = 'Google denied this project access to the configured Gemini Live model.';
      await page.route('**/api/telephony/voice-preview*', (route) =>
        route.fulfill({
          status: 502,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: {
              error: { code: 'voice_preview_unavailable', message: accessMessage },
            },
          }),
        })
      );
      await playBtn.click();
      await expect(page.locator('[data-testid="voice-preview-error"]')).toContainText(accessMessage);
    }

    // 9e. Test Greeting Preview Button
    console.log('Testing bespoke greeting preview button...');
    const greetingBtn = page.locator('[data-testid="greeting-preview-card"] button').first();
    await expect(greetingBtn).toBeVisible();
    await greetingBtn.click();
    await page.waitForTimeout(1000);
    // Indicator or active playing state
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await page.waitForTimeout(500);
    } else if (await page.locator('text=Stop Greeting').isVisible()) {
      await page.locator('text=Stop Greeting').click();
      await page.waitForTimeout(500);
    }

    // 10. Select a voice from the active provider's list.
    const selectVoiceBtn = page.locator(`[data-testid="voice-select-btn-${previewVoice.id}"]`);
    await selectVoiceBtn.click();
    await page.waitForTimeout(800);

    await expect(previewCard).toContainText(/Selected/i);

    // 11. Test Acoustic Calibration Sliders
    console.log('Testing speed slider...');
    const speedSlider = page.locator('[data-testid="speed-slider"]');
    await expect(speedSlider).toBeVisible();

    // 12. Verify Unsaved changes bar appeared
    const unsavedBar = page.locator('[data-testid="agent-studio-unsaved"]');
    await expect(unsavedBar).toBeVisible({ timeout: 5000 });

    // 13. Save changes
    const saveBtn = page.locator('[data-testid="agent-save"]');
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();
    await page.waitForTimeout(2000);

    // 14. Test Live Browser Test Call Initiation from Voice Tab
    console.log('Testing Test Live Agent button from Voice Tab...');
    const testLiveBtn = page.locator('[data-testid="voice-open-test-call-btn"]');
    await expect(testLiveBtn).toBeVisible();
    await testLiveBtn.click();
    await page.waitForTimeout(1200);

    // Verify modal is open and AgentTestCallPanel mounted without crashing
    const testCallPanel = page.locator('[data-testid="agent-test-call-panel"]');
    await expect(testCallPanel).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Unable to initialize test call')).not.toBeVisible();

    // Verify Start Call button is present and enabled
    const startCallBtn = page.locator('[data-testid="test-call-start-browser"]');
    await expect(startCallBtn).toBeVisible();
    await expect(startCallBtn).toBeEnabled();

    await page.evaluate(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Permission denied', 'NotAllowedError'); };
      Object.defineProperty(navigator.permissions, 'query', {
        configurable: true,
        value: async () => ({ state: 'denied' }),
      });
      window.__webAgentSocketRequests = [];
      class TestWebSocket {
        static OPEN = 1;

        constructor(url, protocols) {
          this.url = String(url);
          this.protocols = protocols;
          this.readyState = 0;
          window.__webAgentSocketRequests.push({ url: this.url, protocols });
          queueMicrotask(() => {
            this.readyState = TestWebSocket.OPEN;
            this.onmessage?.({
              data: JSON.stringify({ type: 'ready', callId: 'playwright-ui-call', sampleRate: 16000 }),
            });
          });
        }

        send() {}

        close() {
          this.readyState = 3;
          this.onclose?.();
        }
      }
      window.WebSocket = TestWebSocket;
    });
    await startCallBtn.click();
    const endCallBtn = page.locator('[data-testid="test-call-end-browser"]');
    await expect(endCallBtn).toBeVisible({ timeout: 10000 });
    await expect(testCallPanel).toContainText('Connected in listen-only mode');
    const browserCallRequest = await page.evaluate(() =>
      window.__webAgentSocketRequests.find(({ url }) => new URL(url).pathname === '/ws/web-agent') || null
    );
    expect(browserCallRequest).toBeTruthy();
    const browserCallUrl = new URL(browserCallRequest.url);
    expect(browserCallUrl.searchParams.has('token')).toBe(false);
    expect(browserCallUrl.searchParams.get('language')).toBe('te-IN');
    expect(browserCallRequest.protocols[0]).toBe('voxly-web-agent');
    expect(browserCallRequest.protocols[1]).toMatch(/^voxly-auth\./);
    await endCallBtn.click();

    // Capture screenshot of the test call panel
    const testCallScreenshotPath = testInfo.outputPath('test_call_panel_verified.png');
    await page.screenshot({ path: testCallScreenshotPath });
    console.log('Saved test call modal screenshot to:', testCallScreenshotPath);

    // Close modal
    const closeBtn = page.locator('button[aria-label="Close modal"], button:has-text("✕")').first();
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }

    // 15. Capture high-res screenshots for visual verification
    const artifactPath = testInfo.outputPath('voice_language_studio.png');
    await page.screenshot({ path: artifactPath, fullPage: false });
    console.log('Saved screenshot to:', artifactPath);

    // Scroll to voice showcase cards to highlight play buttons and voice catalog
    const showcase = page.locator('[data-testid="speaking-voice-showcase"]');
    await showcase.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const showcasePath = testInfo.outputPath('voice_cards_playback.png');
    await page.screenshot({ path: showcasePath, fullPage: false });
    console.log('Saved showcase screenshot to:', showcasePath);

    // Verify no unexpected React crashes
    const fatalErrors = consoleErrors.filter(
      (e) => e.includes('Minified React error') || e.includes('is not a function')
    );
    expect(fatalErrors).toHaveLength(0);
    console.log('Voice and Language studio verified successfully with Playwright!');
  });

  test('tenant voice tiers hide unready profiles, clear dependent choices, and save only approved aliases', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);
    await page.goto(`/#dashboard/employees?step=overview&agent=${testAgent.id}`);
    await page.waitForTimeout(2000);

    const voiceTab = page.locator('#agent-tab-voice');
    if (!(await voiceTab.isVisible())) {
      await page.goto('/#dashboard/employees');
      await page.waitForTimeout(1500);
      const agentCard = page.locator('[data-testid="agent-card"]').first();
      await expect(agentCard).toBeVisible();
      await agentCard.click({ force: true });
      await page.waitForTimeout(2000);
    }
    await expect(voiceTab).toBeVisible({ timeout: 15000 });
    await voiceTab.click();

    const selector = page.locator('[data-testid="voice-stack-selector"]');
    await expect(selector).toBeVisible();
    await expect(selector).not.toContainText('Internal Live Provider');
    await expect(page.locator('[data-testid="voice-stack-tier-premium"]')).toHaveCount(0);

    const standardTier = page.locator('[data-testid="voice-stack-tier-medium"]');
    await standardTier.focus();
    await page.keyboard.press('Space');
    await expect(standardTier).toBeChecked();

    const engine = page.locator('[data-testid="voice-stack-engine"]');
    const model = page.locator('[data-testid="voice-stack-model"]');
    const voice = page.locator('[data-testid="voice-stack-voice"]');
    await engine.selectOption('regional-expressive');
    await model.selectOption('regional-fast');
    await voice.selectOption('voice-regional-te');

    await engine.selectOption('turbo-natural');
    await expect(model).toHaveValue('');
    await expect(voice).toHaveValue('');
    await engine.selectOption('regional-expressive');
    await model.selectOption('regional-fast');
    await voice.selectOption('voice-regional-te');
    await expect(page.locator('[data-testid="voice-stack-preview"]')).toContainText('No approved audio sample');

    const save = page.locator('[data-testid="voice-stack-save"]');
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.locator('[data-testid="voice-stack-save-status"]')).toContainText('Voice setup saved.');
    expect(voiceStackPatchBody).toEqual({
      defaultTier: 'medium',
      expectedVoiceRevision: 0,
      voiceSettings: {
        stackSelectionVersion: 1,
        profileRevision: 5,
        engineId: 'regional-expressive',
        modelId: 'regional-fast',
        voiceId: 'voice-regional-te',
      },
    });
    await expect(selector).not.toContainText(/voice-regional-te|regional-fast|regional-expressive/i);

    await page.reload();
    await page.waitForTimeout(1000);
    await page.goto(`/#dashboard/employees?step=overview&agent=${testAgent.id}`);
    await page.waitForTimeout(2000);
    const reloadedVoiceTab = page.locator('#agent-tab-voice');
    if (!(await reloadedVoiceTab.isVisible())) {
      await page.goto('/#dashboard/employees');
      await page.waitForTimeout(1500);
      const agentCard = page.locator('[data-testid="agent-card"]').first();
      await expect(agentCard).toBeVisible();
      await agentCard.click({ force: true });
      await page.waitForTimeout(2000);
    }
    await expect(reloadedVoiceTab).toBeVisible({ timeout: 15000 });
    await reloadedVoiceTab.click();
    await expect(page.locator('[data-testid="voice-stack-selector"]')).toContainText('Saved configuration: Standard Regional Tier');
  });
});
