import { test, expect } from '@playwright/test';
import { setupVoiceWorkspace } from './fixtures/voice-setup.js';

// Mocked API only: no backend, no carrier, no real calls.
// Wherever a "call back in another language" request shows up, the requested
// language is tagged, and Leads sub-tabs count the work waiting behind them.

const AGENT = 'voice-setup-agent';
const iso = (minutesAgo) => new Date(Date.now() - minutesAgo * 60_000).toISOString();

const languageRequests = [
  { id: 'ls-1', kind: 'language_switch', callId: 'call-hindi', agentId: AGENT, phone: '+919000000021', contactName: 'Ravi',
    requestedLanguage: 'hi-IN', requestedLanguageLabel: 'Hindi', originalLanguage: 'te-IN', originalLanguageLabel: 'Telugu',
    requestText: 'Hindi mein baat karo', status: 'pending', error: null, campaignId: null, callbackCallId: null,
    createdAt: iso(30), completedAt: null },
  { id: 'ls-2', kind: 'language_switch', callId: 'call-tamil', agentId: AGENT, phone: '+919000000022', contactName: null,
    requestedLanguage: 'ta-IN', requestedLanguageLabel: 'Tamil', originalLanguage: 'te-IN', originalLanguageLabel: 'Telugu',
    requestText: '', status: 'pending', error: null, campaignId: null, callbackCallId: null, createdAt: iso(60), completedAt: null },
];

const NOTE = 'Used the standard Hindi goodbye because your custom one is in Telugu. Add a Hindi version in the script.';

async function setup(page) {
  await setupVoiceWorkspace(page);
  const state = { dials: [] };
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path === '/api/language-switch-requests') return route.fulfill({ json: { requests: languageRequests, languages: [] } });
    if (path === '/api/language-switch-requests/readiness') {
      return route.fulfill({ json: { ready: true, language: 'hi-IN', code: 'ready', note: NOTE, message: 'Ready.',
        substitutions: [{ line: 'farewell', fromLanguage: 'te-IN', toLanguage: 'hi-IN' }] } });
    }
    if (path === '/api/language-switch-requests/ls-1/call') {
      state.dials.push(req.postDataJSON?.() || {});
      return route.fulfill({ json: { ok: true, itemId: 'ls-1', language: 'hi-IN', dialRequestId: 'ls:x', note: NOTE,
        substitutions: [{ line: 'farewell', fromLanguage: 'te-IN', toLanguage: 'hi-IN' }] } });
    }
    if (path === '/api/follow-ups') {
      return route.fulfill({ json: { total: 1, jobs: [
        { id: 'job-1', agentId: AGENT, kind: 'callback', phone: '+919000000021', status: 'needs_review', reason: 'approval_required',
          timezone: 'Asia/Kolkata', dueAt: iso(-60), expiresAt: iso(-6000), attempts: 0, createdAt: iso(20), updatedAt: iso(20) },
      ] } });
    }
    if (path === '/api/callback-requests') {
      return route.fulfill({ json: { requests: [
        { id: 'cbr-1', callId: 'call-tamil', agentId: AGENT, phone: '+919000000022', status: 'requested',
          requestedWhen: 'Requested during the call', createdAt: iso(50) },
      ] } });
    }
    if (path === '/api/leads') {
      return route.fulfill({ json: { total: 1, stageCounts: { new: 1 }, leads: [
        { leadId: 'lead-1', agentId: AGENT, name: 'Ravi', phone: '+91 90000 00021', stage: 'new', notes: '',
          createdAt: iso(100), updatedAt: iso(30) },
      ] } });
    }
    if (path === '/api/calls') {
      return route.fulfill({ json: { total: 1, limit: 100, offset: 0, calls: [
        { call_id: 'call-hindi', agent_id: AGENT, direction: 'inbound', status: 'completed', connected: true,
          started_at: iso(31), ended_at: iso(30), caller_phone: '+919000000021', duration_sec: 45,
          status_tags: ['followup:language_switch'] },
      ] } });
    }
    if (path === '/api/calls/tags') return route.fulfill({ json: { tags: [] } });
    if (path === '/api/calls/stats') return route.fulfill({ json: { total: 1 } });
    return route.fallback();
  });
  return state;
}

test('Leads sub-tabs count waiting work and every list tags the requested language', async ({ page }) => {
  await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  // The agent's Leads tab counts follow-ups needing review, callback requests and language callbacks.
  await expect(page.getByTestId('agent-calls-tab-count-leads')).toContainText('4');
  await page.getByTestId('agent-calls-panel-tab-leads').click();

  await expect(page.getByTestId('leads-tab-count-followups')).toContainText('2');
  await expect(page.getByTestId('leads-tab-count-language')).toContainText('2');
  await expect(page.getByTestId('leads-tab-pipeline').getByTestId(/leads-tab-count/)).toHaveCount(0);

  // The lead whose caller asked for Hindi says so on its row and in its detail.
  const row = page.getByTestId('lead-row-lead-1');
  await expect(row.getByTestId('language-tag')).toHaveText(/Wants Hindi/);
  await row.getByRole('button', { name: 'Open Ravi' }).click();
  await expect(page.getByTestId('lead-language')).toContainText('Wants Hindi');
  await page.keyboard.press('Escape');

  // Follow-ups and callback requests carry the language their caller asked for.
  await page.getByTestId('leads-tab-followups').click();
  await expect(page.getByTestId('followup-queue').getByTestId('language-tag')).toHaveText(/Wants Hindi/);
  await expect(page.getByTestId('callback-request-list').getByTestId('language-tag')).toHaveText(/Wants Tamil/);

  // The language callbacks list tags each row with its language.
  await page.getByTestId('leads-tab-language').click();
  const list = page.getByTestId('language-callback-list');
  await expect(list.getByTestId('language-tag')).toHaveText([/Wants Hindi/, /Wants Tamil/]);
});

test('calling back in Hindi is never blocked and says which line was replaced', async ({ page }) => {
  const state = await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await page.getByTestId('leads-tab-language').click();
  await page.getByRole('button', { name: 'Call now in Hindi' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Calling Ravi in Hindi' })).toBeVisible();
  await expect(page.getByTestId('language-callback-hint')).toHaveText(NOTE);
  expect(state.dials).toHaveLength(1);
});

test('call history tags the call where the caller asked for another language', async ({ page }) => {
  await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-history').click();
  const row = page.getByTestId(/^call-row-/).filter({ hasText: '+91 90000 00021' });
  await expect(row).toContainText('Callback in another language');
  await expect(row.getByTestId('language-tag')).toHaveText(/Asked for Hindi/);
});

test('Home feed rows and the detail panel show the requested language and the substitution note', async ({ page }) => {
  await setupVoiceWorkspace(page);
  const pinned = [{
    id: 'language:ls-1', type: 'language.callback', category: 'calls', at: iso(5), tone: 'warning', actor: null,
    text: 'Ravi needs a callback in Hindi', detail: 'Hindi mein baat karo', agentId: AGENT,
    contact: { name: 'Ravi', phone: '+91 90000 00021' }, needsAction: true,
    actions: [{ kind: 'dismiss_language', label: 'Dismiss', requestId: 'ls-1' }],
    refs: { languageRequestId: 'ls-1' }, meta: { language: 'hi-IN', languageLabel: 'Hindi' },
  }];
  const items = [{
    id: 'call:cb-1', type: 'call.completed', category: 'calls', at: iso(2), tone: 'neutral', actor: 'Hima',
    text: 'called Ravi', detail: null, agentId: AGENT, contact: { name: 'Ravi' }, needsAction: false, actions: [],
    refs: { callId: 'cb-1' }, meta: { callLanguage: 'hi-IN', callLanguageLabel: 'Hindi', languageNote: NOTE },
  }];
  await page.route('**/api/activity/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/feed')) return route.fulfill({ json: { items, pinned, needsActionCount: 1, nextCursor: null } });
    if (url.pathname.endsWith('/item')) {
      const id = url.searchParams.get('id');
      const item = [...pinned, ...items].find((it) => it.id === id);
      return route.fulfill({ json: { item, facts: id.startsWith('language:') ? { status: 'pending', language: 'Hindi', originalLanguage: 'Telugu' } : {}, related: {} } });
    }
    return route.fulfill({ json: { calls: [], counts: {}, items: [] } });
  });
  await page.goto('/#dashboard/overview');
  const languageRow = page.locator('[data-item-id="language:ls-1"]').first();
  await expect(languageRow.getByTestId('language-tag')).toHaveText(/Wants Hindi/);
  const callRow = page.locator('[data-item-id="call:cb-1"]').first();
  await expect(callRow.getByTestId('language-tag')).toHaveText(/Called in Hindi/);

  await callRow.getByTestId('feed-item-open').click();
  await expect(page.getByTestId('language-note')).toHaveText(NOTE);
});

test('language tags and sub-tab counts fit a phone screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.getByTestId('agent-tab-calls').click();
  await page.getByTestId('agent-calls-panel-tab-leads').click();
  await expect(page.getByTestId('leads-tab-count-language')).toBeVisible();
  for (const tab of ['pipeline', 'followups', 'language']) {
    await page.getByTestId(`leads-tab-${tab}`).click();
    await expect(page.locator('[data-testid="language-tag"]:visible').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  }
});
