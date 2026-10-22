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
              retailRate: { usdMicrosPerMin: 7000, inrPaisePerMin: 70, version: 1, complete: true },
              engines: [
                {
                  id: 'turbo-natural',
                  label: 'Turbo Natural Engine',
                  models: [{
                    id: 'turbo-regional',
                    label: 'Turbo Regional',
                    voices: [{ id: 'voice-economical-te', label: 'Telugu Assistant', languages: ['te-IN', 'hi-IN', 'en-IN'] }],
                  }],
                },
              ],
            },
            {
              tier: 'medium',
              label: 'Standard Regional Tier',
              ready: true,
              profileRevision: 5,
              retailRate: { usdMicrosPerMin: 14000, inrPaisePerMin: 140, version: 1, complete: true },
              engines: [
                {
                  id: 'regional-expressive',
                  label: 'Regional Expressive Engine',
                  models: [{
                    id: 'regional-fast',
                    label: 'Regional Fast',
                    audioStreaming: true,
                    voices: [{ id: 'voice-regional-te', label: 'Telugu Support', languages: ['te-IN', 'hi-IN', 'en-IN'] }],
                  }],
                },
                {
                  id: 'turbo-natural',
                  label: 'Turbo Natural Engine',
                  models: [{
                    id: 'turbo-standard',
                    label: 'Turbo Standard',
                    voices: [{ id: 'voice-standard-te', label: 'Telugu Assistant', languages: ['te-IN', 'hi-IN', 'en-IN'] }],
                  }],
                },
              ],
            },
            {
              tier: 'premium',
              label: 'Internal Live Provider',
              ready: true,
              profileRevision: 8,
              retailRate: { usdMicrosPerMin: 42000, inrPaisePerMin: 420, version: 1, complete: true },
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
            ...(body.languages ? { languages: body.languages } : {}),
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

  async function openVoiceStudio(page) {
    await page.goto(`/#dashboard/employees?step=voice&agent=${testAgent.id}`);
    await expect(page.getByTestId('agent-tab-voice')).toBeVisible();
    await page.getByTestId('agent-tab-voice').click();
    await expect(page.getByTestId('agent-voice-panel')).toBeVisible();
  }

  test('saved spoken language wins over stale English voice metadata in browser tests', async ({ page }) => {
    await page.route('**/business-brain', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({
        draft: { sections: [{ title: 'saas_voice_config', raw_text: JSON.stringify({ language: 'en-IN', realtimeVoice: 'Puck' }) }] },
      }),
    }));
    let socketUrl = '';
    await page.routeWebSocket(/\/ws\/web-agent(?:\?|$)/, (socket) => {
      socketUrl = socket.url();
      socket.send(JSON.stringify({ type: 'ready', callId: 'mock-language-call', sampleRate: 16000 }));
    });
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); };
    });
    await openVoiceStudio(page);
    await expect(page.getByTestId('language-selection-card')).toContainText('Active: Telugu (te-IN)');
    await page.getByTestId('voice-open-test-call-btn').click();
    await page.getByTestId('test-call-start-browser').click();
    await expect(page.getByTestId('test-call-end-browser')).toBeVisible();
    expect(new URL(socketUrl).searchParams.get('language')).toBe('te-IN');
    await page.getByTestId('test-call-end-browser').click();
  });

  test('premium voice is saved atomically and survives a reload with stale brain metadata', async ({ page }) => {
    let releaseSave;
    const saveAllowed = new Promise((resolve) => { releaseSave = resolve; });
    await page.route(`**/api/agents/${testAgent.id}`, async (route) => {
      if (route.request().method() === 'PATCH') await saveAllowed;
      await route.fallback();
    });
    await page.route('**/business-brain', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({
        draft: { sections: [{ title: 'saas_voice_config', raw_text: JSON.stringify({ language: 'en-IN', realtimeVoice: 'te-in-csagent-5' }) }] },
      }),
    }));
    await openVoiceStudio(page);
    await page.getByTestId('voice-tier-select-btn-te-in-csagent-4').click();
    await expect(page.getByTestId('voice-tier-select-btn-te-in-csagent-4')).toContainText('Saving…');
    await expect(page.getByTestId('voice-open-test-call-btn')).toBeDisabled();
    await expect(page.getByTestId('agent-test-call')).toBeDisabled();
    releaseSave();
    await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved.');
    expect(voiceStackPatchBody).toMatchObject({
      defaultTier: 'premium', expectedVoiceRevision: 0,
      voiceSettings: { stackSelectionVersion: 1, realtimeVoice: 'te-in-csagent-4' },
    });
    expect(voiceStackPatchBody.voiceSettings).not.toHaveProperty('voiceId');
    await expect(page.getByTestId('voice-open-test-call-btn')).toBeEnabled();
    await page.reload();
    await page.getByTestId('agent-tab-voice').click();
    await expect(page.getByTestId('voice-select-btn-te-in-csagent-4')).toContainText('Selected');
    await expect(page.getByTestId('voice-select-btn-te-in-csagent-5')).toContainText('Choose');
  });

  test('a conflicting tier save keeps the draft unsaved and blocks stale test calls until reload', async ({ page }) => {
    persistedTestAgent = {
      ...testAgent, defaultTier: 'medium', voiceRevision: 1,
      voiceSettings: { stackSelectionVersion: 1, profileRevision: 5, engineId: 'regional-expressive', modelId: 'regional-fast', voiceId: 'voice-regional-te' },
    };
    await page.route(`**/api/agents/${testAgent.id}`, async (route) => {
      if (route.request().method() !== 'PATCH') return route.fallback();
      persistedTestAgent = { ...persistedTestAgent, voiceRevision: 2 };
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: { error: { code: 'voice_revision_conflict', message: 'Voice settings changed.' } } }) });
    });
    await openVoiceStudio(page);
    await page.getByTestId('voice-select-btn-voice-economical-te').click();
    await expect(page.getByTestId('voice-stack-save-error')).toContainText('Your choice was not applied');
    await expect(page.getByTestId('voice-stack-save-status')).toHaveCount(0);
    await expect(page.getByTestId('voice-stack-tier-low')).toBeChecked();
    await expect(page.getByTestId('agent-test-call')).toBeDisabled();
    await page.getByTestId('voice-stack-conflict-reload').click();
    await expect(page.getByTestId('voice-stack-tier-medium')).toBeChecked();
    await expect(page.getByTestId('voice-stack-save-error')).toHaveCount(0);
    await expect(page.getByTestId('agent-test-call')).toBeEnabled();
  });

  test('profile revision conflicts refresh the catalog and can save again without a false editor conflict', async ({ page }) => {
    let profileRevision = 5;
    let catalogReads = 0;
    let rejectFirstSave = true;
    await page.route('**/api/voice-stacks/catalog*', (route) => {
      catalogReads += 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ profiles: [{
        tier: 'medium', ready: true, profileRevision,
        retailRate: { usdMicrosPerMin: 14000, inrPaisePerMin: 140, version: 1, complete: true },
        engines: [{ id: 'regional-expressive', label: 'Regional Expressive Engine', models: [{
          id: 'regional-fast', label: 'Regional Fast', audioStreaming: true,
          voices: [{ id: 'voice-regional-te', label: 'Telugu Support', languages: ['te-IN'] }],
        }] }],
      }] }) });
    });
    await page.route(`**/api/agents/${testAgent.id}`, async (route) => {
      if (route.request().method() !== 'PATCH' || !rejectFirstSave) return route.fallback();
      rejectFirstSave = false;
      profileRevision = 6;
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: { error: {
        code: 'profile_revision_conflict', message: 'The selected voice profile changed. Reload the voice catalog and save again.',
      } } }) });
    });
    await openVoiceStudio(page);
    await page.getByTestId('voice-select-btn-voice-regional-te').click();
    await expect(page.getByTestId('voice-stack-save-error')).toContainText('Voice options changed');
    await expect(page.getByTestId('voice-stack-save-error')).not.toContainText('Another editor');
    await expect(page.getByTestId('voice-stack-conflict-reload')).toHaveCount(0);
    expect(catalogReads).toBeGreaterThanOrEqual(2);
    await page.getByTestId('voice-select-btn-voice-regional-te').click();
    await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
    expect(voiceStackPatchBody).toMatchObject({ expectedVoiceRevision: 0, voiceSettings: { profileRevision: 6 } });
  });

  for (const [code, message] of [
    ['invalid_composed_tier', 'This voice tier could not be applied'],
    ['voice_selection_invalid', 'That voice is no longer available for this language'],
    ['profile_unavailable', 'This voice tier is currently unavailable'],
    ['unsupported_language', 'This tier does not support the selected language'],
  ]) {
    test(`${code} is shown as a voice configuration failure, not a newer editor`, async ({ page }) => {
      await page.route(`**/api/agents/${testAgent.id}`, async (route) => {
        if (route.request().method() !== 'PATCH') return route.fallback();
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: { error: { code, message: 'Voice configuration rejected.' } } }) });
      });
      await openVoiceStudio(page);
      await page.getByTestId('voice-tier-select-btn-te-in-csagent-4').click();
      await expect(page.getByTestId('voice-stack-save-error')).toContainText(message);
      await expect(page.getByTestId('voice-stack-save-error')).not.toContainText('Another editor');
      await expect(page.getByTestId('voice-stack-conflict-reload')).toHaveCount(0);
      await expect(page.getByTestId('voice-open-test-call-btn')).toBeDisabled();
      await expect(page.getByTestId('voice-stack-save-status')).toHaveCount(0);
    });
  }

  test('sequential economical, standard, premium and reloaded saves use the latest durable revision', async ({ page }) => {
    const patches = [];
    page.on('request', (request) => {
      if (request.method() === 'PATCH' && new URL(request.url()).pathname === `/api/agents/${testAgent.id}`) patches.push(request.postDataJSON());
    });
    await openVoiceStudio(page);
    for (const [tier, voiceId] of [
      ['low', 'voice-economical-te'], ['medium', 'voice-regional-te'], ['premium', 'te-in-csagent-4'],
    ]) {
      const button = page.getByTestId(tier === 'premium' ? `voice-select-btn-${voiceId}` : `voice-select-btn-${voiceId}`);
      await button.click();
      await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
      await expect(page.getByTestId(`voice-stack-tier-${tier}`)).toBeChecked();
    }
    expect(patches.map((patch) => patch.expectedVoiceRevision)).toEqual([0, 1, 2]);
    expect(patches[2].voiceSettings).toEqual({ stackSelectionVersion: 1, realtimeVoice: 'te-in-csagent-4' });
    await page.reload();
    await page.getByTestId('agent-tab-voice').click();
    await expect(page.getByTestId('voice-select-btn-te-in-csagent-4')).toContainText('Selected');
    await page.getByTestId('voice-select-btn-voice-economical-te').click();
    await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
    expect(patches[3]).toMatchObject({ defaultTier: 'low', expectedVoiceRevision: 3 });
    await expect(page.getByTestId('voice-stack-save-error')).toHaveCount(0);
  });

  test('an unconfirmed premium save cannot report success or start a stale voice test', async ({ page }) => {
    await page.route(`**/api/agents/${testAgent.id}`, async (route) => {
      if (route.request().method() !== 'PATCH') return route.fallback();
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ agent: {
        ...testAgent, defaultTier: 'premium', voiceRevision: 1,
        voiceSettings: { stackSelectionVersion: 1, realtimeVoice: 'te-in-csagent-5' },
      } }) });
    });
    await openVoiceStudio(page);
    await page.getByTestId('voice-tier-select-btn-te-in-csagent-4').click();
    await expect(page.getByTestId('voice-stack-save-error')).toContainText('save could not be confirmed');
    await expect(page.getByTestId('voice-stack-save-status')).toHaveCount(0);
    await expect(page.getByTestId('voice-open-test-call-btn')).toBeDisabled();
    await expect(page.getByTestId('agent-test-call')).toBeDisabled();
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
    const renderedVoiceName = (await previewCard.locator('span.font-bold').innerText().catch(() => '')) || 'Voice';
    await expect(playingIndicator).toContainText(new RegExp(renderedVoiceName || previewVoice.label || previewVoice.name || 'Voice', 'i'));
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

  test('tenant voice tiers use native rates, isolate voices, and persist exact aliases and revisions', async ({ page }) => {
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
    await expect(page.locator('[data-testid="voice-stack-tier-premium"]')).toBeEnabled();
    await expect(selector).toContainText('₹0.70 per min');

    await page.getByTestId('voice-stack-tier-low').check();
    await expect(page.getByTestId('speaking-voice-showcase')).toHaveCount(0);
    await expect(page.getByTestId('voice-stack-options')).toHaveCount(0);

    await page.getByTestId('voice-stack-tier-premium').check();
    await expect(page.getByTestId('speaking-voice-showcase')).toBeVisible();

    const standardTier = page.locator('[data-testid="voice-stack-tier-medium"]');
    await standardTier.focus();
    await page.keyboard.press('Space');
    await expect(standardTier).toBeChecked();

    const selectMediumVoiceBtn = page.locator('[data-testid="voice-select-btn-voice-regional-te"]');
    await expect(selectMediumVoiceBtn).toBeVisible();
    await selectMediumVoiceBtn.click();
    await expect(page.locator('[data-testid="voice-stack-save-status"]')).toContainText('Voice setup saved.');
    expect(voiceStackPatchBody).toMatchObject({
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

    // A new profile revision needs a fresh save even when its public choices did not change.
    await page.route('**/api/voice-stacks/catalog*', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ profiles: [{
        tier: 'medium', ready: true, profileRevision: 6,
        retailRate: { usdMicrosPerMin: 14000, inrPaisePerMin: 140, version: 1, complete: true },
        engines: [{ id: 'regional-expressive', label: 'Regional Expressive Engine', models: [{
          id: 'regional-fast', label: 'Regional Fast', audioStreaming: true,
          voices: [{ id: 'voice-regional-te', label: 'Telugu Support', languages: ['te-IN'] }],
        }] }],
      }] }),
    }));
    await page.reload();
    await page.getByTestId('agent-tab-voice').click();
    const reselectMediumVoiceBtn = page.locator('[data-testid="voice-select-btn-voice-regional-te"]');
    await expect(reselectMediumVoiceBtn).toBeVisible();
    await reselectMediumVoiceBtn.click();
    await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved.');
    expect(voiceStackPatchBody.expectedVoiceRevision).toBe(1);
    expect(voiceStackPatchBody.voiceSettings.profileRevision).toBe(6);
  });

  test('unconfigured tiers stay visible and disabled without borrowing live voices', async ({ page }) => {
    await page.route('**/api/voice-stacks/catalog*', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ profiles: [
        { tier: 'low', ready: false, profileRevision: 0, engines: [], retailRate: null },
        { tier: 'medium', ready: false, profileRevision: 0, engines: [], retailRate: null },
        { tier: 'premium', ready: true, profileRevision: 1, engines: [],
          retailRate: { usdMicrosPerMin: 42000, inrPaisePerMin: 420, version: 1, complete: true } },
      ] }),
    }));
    await page.goto(`/#dashboard/employees?step=voice&agent=${testAgent.id}`);
    await expect(page.getByTestId('voice-stack-tier-low')).toBeDisabled();
    await expect(page.getByTestId('voice-stack-tier-medium')).toBeDisabled();
    await expect(page.getByTestId('voice-stack-selector')).toContainText('Unavailable for this language until setup is approved.');
    await page.getByTestId('voice-stack-tier-premium').check();
    await expect(page.getByTestId('voice-stack-options')).toHaveCount(0);
    await expect(page.getByTestId('speaking-voice-showcase')).toBeVisible();
  });

  test('three stack columns render scrollable voice lists and play back voice previews across tiers according to selected language', async ({ page }) => {
    let lastPreviewPayload = null;
    const previewSample = path.resolve(__dirname, '../public/audio/voxly/samples/marin.wav');
    await page.route('**/api/telephony/voice-preview*', async (route) => {
      lastPreviewPayload = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: fs.readFileSync(previewSample) });
    });

    await page.goto('/#dashboard/overview');
    await page.waitForTimeout(1000);
    await page.goto(`/#dashboard/employees?step=voice&agent=${testAgent.id}`);
    await page.waitForTimeout(2000);

    const voiceTab = page.locator('#agent-tab-voice');
    if (!(await voiceTab.isVisible())) {
      await page.goto('/#dashboard/employees');
      await page.waitForTimeout(1500);
      const agentCard = page.locator('[data-testid="agent-card"]').first();
      await agentCard.click({ force: true });
      await page.waitForTimeout(2000);
    }
    await expect(voiceTab).toBeVisible({ timeout: 15000 });
    await voiceTab.click();

    // 1. Verify 3 stack tier columns exist
    await expect(page.locator('[data-testid="voice-stack-tier-low"]')).toBeVisible();
    await expect(page.locator('[data-testid="voice-stack-tier-medium"]')).toBeVisible();
    await expect(page.locator('[data-testid="voice-stack-tier-premium"]')).toBeVisible();

    // 2. Verify scrollable roster containers inside columns
    const scrollableRosters = page.locator('.max-h-60.overflow-y-auto');
    expect(await scrollableRosters.count()).toBeGreaterThanOrEqual(3);

    // 3. Play sample in Low tier (Telugu is default active language)
    const playLowBtn = page.locator('[data-testid="voice-play-btn-voice-economical-te"]');
    await expect(playLowBtn).toBeVisible();
    lastPreviewPayload = null;
    await playLowBtn.click();
    await page.waitForTimeout(500);

    expect(lastPreviewPayload).toBeTruthy();
    expect(lastPreviewPayload.tier).toBe('low');
    expect(lastPreviewPayload.language).toBe('te-IN');
    expect(lastPreviewPayload.voiceId).toBe('voice-economical-te');
    expect(lastPreviewPayload.text).toContain('నమస్కారం');

    // 4. Play sample in Medium tier
    const playMedBtn = page.locator('[data-testid="voice-play-btn-voice-regional-te"]');
    await expect(playMedBtn).toBeVisible();
    lastPreviewPayload = null;
    await playMedBtn.click();
    await page.waitForTimeout(500);

    expect(lastPreviewPayload).toBeTruthy();
    expect(lastPreviewPayload.tier).toBe('medium');
    expect(lastPreviewPayload.language).toBe('te-IN');
    expect(lastPreviewPayload.voiceId).toBe('voice-regional-te');
    expect(lastPreviewPayload.text).toContain('నమస్కారం');

    // 5. Switch Language to Hindi (hi-IN)
    const hindiCard = page.locator('[data-testid="language-card-hi-IN"]');
    await expect(hindiCard).toBeVisible();
    await hindiCard.click();
    await page.waitForTimeout(600);

    // Play sample in Low tier with Hindi active - text should now be Hindi
    lastPreviewPayload = null;
    await playLowBtn.click();
    await page.waitForTimeout(500);

    expect(lastPreviewPayload).toBeTruthy();
    expect(lastPreviewPayload.tier).toBe('low');
    expect(lastPreviewPayload.language).toBe('hi-IN');
    expect(lastPreviewPayload.voiceId).toBe('voice-economical-te');
    expect(lastPreviewPayload.text).toContain('नमस्ते');

    // Play sample in Medium tier with Hindi active
    lastPreviewPayload = null;
    await playMedBtn.click();
    await page.waitForTimeout(500);

    expect(lastPreviewPayload).toBeTruthy();
    expect(lastPreviewPayload.tier).toBe('medium');
    expect(lastPreviewPayload.language).toBe('hi-IN');
    expect(lastPreviewPayload.voiceId).toBe('voice-regional-te');
    expect(lastPreviewPayload.text).toContain('नमस्ते');

    // 6. Switch back to persisted language (te-IN) to allow saving voice setup
    const teluguCard = page.locator('[data-testid="language-card-te-IN"]');
    await expect(teluguCard).toBeVisible();
    await teluguCard.click();
    await page.waitForTimeout(600);

    // 7. Test voice selection in Low tier
    const selectLowBtn = page.locator('[data-testid="voice-select-btn-voice-economical-te"]');
    await expect(selectLowBtn).toBeVisible();
    await selectLowBtn.click();
    await page.waitForTimeout(500);

    // Verify low radio button is now checked
    await expect(page.locator('[data-testid="voice-stack-tier-low"]')).toBeChecked();
    await expect(page.locator('[data-testid="voice-stack-save-status"]')).toContainText('Voice setup saved.');

    expect(voiceStackPatchBody).toMatchObject({
      defaultTier: 'low',
      voiceSettings: {
        stackSelectionVersion: 1,
        voiceId: 'voice-economical-te',
      },
    });
  });
});
