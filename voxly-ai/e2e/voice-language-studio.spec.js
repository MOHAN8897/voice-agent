import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { buildEmployee } from './helpers/api.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionPath = path.resolve(__dirname, '../../data/e2e_session.json');

test.describe('Voice and Language Configuration in Agent Console', () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on('pageerror', (err) => {
      console.log('BROWSER PAGE ERROR:', err.message);
      consoleErrors.push(err.message);
    });

    // Keep this authenticated UI check read-only and avoid spending live TTS
    // credits: reads use the local test account, while writes and audio previews
    // are fulfilled by Playwright.
    const previewSample = path.resolve(__dirname, '../public/audio/voxly/samples/marin.wav');
    await page.route('**/api/telephony/voice-preview', (route) =>
      route.fulfill({ status: 200, contentType: 'audio/wav', body: fs.readFileSync(previewSample) })
    );
    await page.route('**/api/telephony/voice-options', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          stackLabel: 'Gemini Live',
          defaultVoiceId: 'puck',
          voices: [
            { id: 'puck', label: 'Puck', provider: 'gemini', geminiVoice: 'Puck', category: 'sales', gender: 'male' },
            { id: 'te-in-csagent-4', label: 'Telugu · Male', provider: 'gemini', geminiVoice: 'te-in-csagent-4', languageCode: 'te-IN', accent: 'Telugu', category: 'support', gender: 'male' },
            { id: 'te-in-csagent-5', label: 'Telugu · Female', provider: 'gemini', geminiVoice: 'te-in-csagent-5', languageCode: 'te-IN', accent: 'Telugu', category: 'support', gender: 'female', defaultForLanguage: true, sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?' },
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
    await page.route('**/api/agents/**', async (route) => {
      const method = route.request().method().toUpperCase();
      if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        await route.continue();
        return;
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

    if (fs.existsSync(sessionPath)) {
      const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));
      const u = sess.user;
      const sessionUser = {
        id: u.userId,
        name: u.fullName || u.email,
        email: u.email,
        tenantId: sess.tenant?.tenantId,
        hasCompletedOnboarding: true,
      };

      await page.addInitScript(
        ({ token, sessionUser, email }) => {
          sessionStorage.setItem('voxly_auth_token', token);
          sessionStorage.setItem('dialtact_auth_token', token);
          localStorage.setItem('voxly_auth_session', JSON.stringify(sessionUser));
          localStorage.setItem('dialtact_auth_session', JSON.stringify(sessionUser));
          localStorage.setItem('voxly_tour_completed', 'true');
          localStorage.setItem('voxly_tour_completed_default', 'true');
          localStorage.setItem(`voxly_tour_completed_${email}`, 'true');
          localStorage.setItem('dialtact_tour_completed_default', 'true');
          localStorage.setItem(`dialtact_tour_completed_${email}`, 'true');

          const style = document.createElement('style');
          style.innerHTML = '.driver-overlay, .driver-popover { display: none !important; pointer-events: none !important; }';
          const installTourStyle = () => {
            const root = document.head || document.documentElement;
            if (root) root.appendChild(style);
          };
          if (document.head || document.documentElement) installTourStyle();
          else document.addEventListener('DOMContentLoaded', installTourStyle, { once: true });
        },
        { token: sess.token, sessionUser, email: u.email }
      );
    }
  });

  test('Voice and Language studio renders cards, plays preconfigured sample playback, and changes voice/language', async ({
    page,
  }, testInfo) => {
    test.skip(!fs.existsSync(sessionPath), 'Missing data/e2e_session.json');
    const sess = JSON.parse(fs.readFileSync(sessionPath, 'utf8'));

    // 1. Navigate to overview first to ensure session bootstrap
    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);

    // Close any driver tour if somehow still mounted
    await page.evaluate(() => {
      document.querySelectorAll('.driver-overlay, .driver-popover').forEach((el) => el.remove());
    });

    // 2. Navigate directly to employee workbench if agentId is known
    const targetAgentId = sess.agentId || '832dd86c-bbd5-4bcc-8466-469b3411c99f';
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
      return fetchPhoneVoiceOptions();
    });
    const activeVoiceProvider = voiceOptions.voices.some((voice) => voice.provider === 'gemini') ? 'gemini' : 'openai';
    const visibleVoiceRows = voiceOptions.voices.filter(
      (voice) => voice.provider === activeVoiceProvider && voice.languageCode === 'te-IN'
    );

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
      await page.route('**/api/telephony/voice-preview', async (route) => {
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
      await page.route('**/api/telephony/voice-preview', (route) =>
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
});
