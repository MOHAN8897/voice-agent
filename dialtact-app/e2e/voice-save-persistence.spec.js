import { test, expect } from '@playwright/test';
import { voiceSetupData } from './fixtures/voice-setup.js';

// "Voice selections are not being saved": every PATCH answered 200, yet the
// screen later showed another voice. The mock below answers with the real
// backend shapes (PATCH/GET /api/agents/{id} → {agent: {voice_settings,
// voice_revision, default_tier, languages}}) and enforces expectedVoiceRevision
// like agent_service.patch_agent, so a stale revision is a 409 here too.
// No call is placed.

const VOICES = ['voice-a', 'voice-b', 'voice-c'];

async function setup(page, { patchDelayMs = 0 } = {}) {
  const data = voiceSetupData();
  const medium = data.profiles.find((p) => p.tier === 'medium');
  medium.engines[0].models[0].voices = VOICES.map((id, i) => ({
    id, label: `Voice ${i + 1}`, languages: ['te-IN', 'hi-IN'], gender: 'female',
  }));
  const server = {
    tier: 'medium',
    languages: ['te-IN'],
    voice: { stackSelectionVersion: 1, profileRevision: 3, engineId: 'engine-medium', modelId: 'model-medium', voiceId: 'voice-a' },
    revision: 1,
    patches: [],
    conflicts: 0,
  };
  const agentRow = () => ({
    agent_id: data.agent.id, name: data.agent.name, status: 'active', default_tier: server.tier,
    languages: server.languages, voice_settings: { ...server.voice }, voice_revision: server.revision,
    voiceRevision: server.revision, active_compiled_brain_version: 'published', environment: 'development',
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body = { ok: true, items: [] };
    let status = 200;
    if (path === '/api/auth/me') body = { user: data.user, tenant: { tenantId: data.user.tenantId }, role: 'owner' };
    else if (path === '/api/auth/session') body = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') body = { agents: [agentRow()] };
    else if (path === '/api/voice-stacks/catalog') body = { profiles: data.profiles };
    else if (path.includes('/voice-options')) body = { voices: [], languages: [{ code: 'te-IN', label: 'Telugu' }] };
    else if (path.endsWith('/billing/wallet')) body = { balanceUsd: 100 };
    else if (path.endsWith('/business-brain')) body = { draft: { revision: 'draft-1', sections: [{ section_id: 'script', type: 'facts', title: 'Calling script', raw_text: 'Hello, I am Hima.', enabled: true, order: 20 }] }, published: { version_id: 'published' } };
    else if (path.endsWith('/telephony-profile')) body = { profile: {} };
    else if (path === `/api/agents/${data.agent.id}`) {
      if (request.method() === 'PATCH') {
        const write = request.postDataJSON();
        if (patchDelayMs) await new Promise((r) => setTimeout(r, patchDelayMs));
        if (write.voiceSettings && write.expectedVoiceRevision !== server.revision) {
          server.conflicts += 1;
          return route.fulfill({ status: 409, json: { detail: { error: { code: 'voice_revision_conflict', message: 'Voice settings changed in another session. Reload before saving.', currentRevision: server.revision } } } });
        }
        server.patches.push(write);
        if (write.defaultTier) server.tier = write.defaultTier;
        if (write.languages) server.languages = write.languages;
        if (write.voiceSettings) {
          server.voice = { ...server.voice, ...write.voiceSettings };
          server.revision += 1;
        }
        body = { ok: true, agent: agentRow() };
      } else {
        body = { agent: agentRow() };
      }
    }
    await route.fulfill({ status, json: body });
  });
  await page.addInitScript(({ user, token }) => {
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_tour_completed_voice-setup@example.invalid', 'true');
  }, data);
  const url = `/#dashboard/employees?step=voice&agent=${data.agent.id}`;
  await page.goto(url);
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  return { server, url };
}

const selected = (page, id) => expect(page.getByTestId(`voice-select-btn-${id}`)).toContainText('Selected');

test('a picked voice is saved, shown as saved, and survives a reload', async ({ page }) => {
  const { server, url } = await setup(page);
  await selected(page, 'voice-a');
  await page.getByTestId('voice-select-btn-voice-b').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  expect(server.patches.at(-1)).toMatchObject({ defaultTier: 'medium', expectedVoiceRevision: 1, voiceSettings: { voiceId: 'voice-b' } });
  await expect(page.getByTestId('agent-studio-unsaved')).toHaveCount(0);
  await page.goto('about:blank');
  await page.goto(url);
  await selected(page, 'voice-b');
  await expect(page.getByTestId('voice-select-btn-voice-a')).toContainText('Choose');
});

test('quick successive picks all persist in order without a revision conflict', async ({ page }) => {
  const { server } = await setup(page, { patchDelayMs: 400 });
  await selected(page, 'voice-a');
  // The row is clickable while the first save is in flight; the second pick is
  // queued and sent with the revision the first save returned.
  await page.getByTestId('voice-select-btn-voice-b').click();
  await page.getByTestId('voice-select-btn-voice-c').locator('xpath=ancestor::div[contains(@class,"cursor-pointer")][1]').click();
  await expect.poll(() => server.voice.voiceId, { timeout: 8000 }).toBe('voice-c');
  expect(server.conflicts).toBe(0);
  expect(server.patches.map((p) => p.expectedVoiceRevision)).toEqual([1, 2]);
  await selected(page, 'voice-c');
  await expect(page.getByTestId('voice-stack-save-error')).toHaveCount(0);
});

test('switching language keeps the saved voice and saves language with the next pick', async ({ page }) => {
  const { server, url } = await setup(page);
  await page.getByTestId('voice-select-btn-voice-b').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  await page.getByTestId('language-card-hi-IN').click();
  // The voice speaks Hindi too, so it stays chosen instead of resetting to Voice 1.
  await selected(page, 'voice-b');
  await expect(page.getByTestId('voice-stack-save-error')).toHaveCount(0);
  await page.getByTestId('voice-select-btn-voice-c').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  expect(server.patches.at(-1)).toMatchObject({ languages: ['hi-IN'], voiceSettings: { voiceId: 'voice-c' } });
  // The language went out with the voice save, so it is not left as an unsaved edit.
  await expect(page.getByTestId('agent-studio-unsaved')).toHaveCount(0);
  await page.goto('about:blank');
  await page.goto(url);
  await expect(page.getByTestId('language-card-hi-IN')).toHaveAttribute('aria-pressed', 'true');
  await selected(page, 'voice-c');
});

test('re-clicking the current language does not change the voice', async ({ page }) => {
  const { server } = await setup(page);
  await page.getByTestId('voice-select-btn-voice-b').click();
  await expect(page.getByTestId('voice-stack-save-status')).toContainText('Voice setup saved');
  await page.getByTestId('language-card-te-IN').click();
  await selected(page, 'voice-b');
  await expect(page.getByTestId('agent-studio-unsaved')).toHaveCount(0);
  expect(server.patches).toHaveLength(1);
});

test('a rejected save shows the error and keeps the saved voice selected', async ({ page }) => {
  const { server } = await setup(page);
  await selected(page, 'voice-a');
  server.revision = 5; // another session saved meanwhile; the page still holds revision 1
  server.voice.voiceId = 'voice-c';
  await page.getByTestId('voice-select-btn-voice-b').click();
  await expect(page.getByTestId('voice-stack-save-error')).toBeVisible();
  await expect(page.getByTestId('voice-stack-save-status')).toHaveCount(0);
  expect(server.voice.voiceId).toBe('voice-c');
});
