import { test, expect } from '@playwright/test';

const agent = { id: 'primary-script-test', agent_id: 'primary-script-test', name: 'Script Test Agent', status: 'active', languages: ['en-IN'] };
const original = '--- AGENT IDENTITY ---\nYou are Meera, representing Example Support.\n\n--- CANONICAL OPENING ---\nSay once:\nHello, how can I help?\n\n--- COMPANY & OFFER ---\nApproved price INR 13750.';
const initialSections = [
  { section_id: 'i', type: 'identity_purpose', title: 'Identity & Purpose', raw_text: 'Preserve this identity note.\nOpening greeting: Hello, how can I help?', enabled: true, order: 10 },
  { section_id: 's', type: 'facts', title: 'Calling script', raw_text: original, enabled: true, order: 20 },
  { section_id: 'g', type: 'guardrails', title: 'Guardrails', raw_text: '- Never promise refunds without approval.', enabled: true, order: 30 },
  { section_id: 'extra', type: 'custom', title: 'Approved escalation policy', raw_text: 'Escalate invoice disputes to finance.', enabled: true, order: 50 },
  { section_id: 'extra-facts', type: 'facts', title: 'Business Facts', raw_text: 'Additional fact: support closes at 18:15.', enabled: true, order: 60 },
  { section_id: 'faq-notes', type: 'faq', title: 'FAQ & Objections', raw_text: 'Unstructured approved FAQ note: escalation requires consent.', enabled: true, order: 40 },
  { section_id: 'v', type: 'custom', title: 'saas_voice_config', raw_text: '{"realtimeVoice":"Puck","language":"en-IN"}', enabled: false, order: 5 },
];

async function setup(page, { failPublish = false, failRead = false, generationReport = null } = {}) {
  const state = { reads: 0, voiceReads: 0, writes: [], publishes: 0, failRead, revision: 'draft-1', sections: structuredClone(initialSections) };
  const user = { id: 'script-test-user', userId: 'script-test-user', fullName: 'Script Tester', name: 'Script Tester', email: 'script-test@example.invalid', hasCompletedOnboarding: true, role: 'subscriber', tenantId: 'script-test-tenant' };
  const b64 = (data) => Buffer.from(JSON.stringify(data)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    let data = { ok: true, items: [] };
    let status = 200;
    if (path === '/api/auth/me') data = { user, tenant: { tenantId: user.tenantId }, role: 'subscriber' };
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [agent] };
    else if (path.includes('/voice-options')) {
      state.voiceReads++;
      data = { activeVoiceProvider: 'gemini', activeModel: 'gemini-3.8-live', defaultVoiceId: 'Puck', voices: [{ id: 'Puck', label: 'Puck', provider: 'gemini' }], languages: [{ code: 'en-IN', label: 'Indian English' }] };
    } else if (path.endsWith('/business-brain') && method === 'GET') {
      state.reads++;
      status = state.failRead ? 503 : 200;
      data = state.failRead ? { detail: 'Script service unavailable' } : { draft: { sections: state.sections, revision: state.revision }, published: { version_id: 'published-original', optimizer_report: generationReport } };
    } else if (path.endsWith('/business-brain/preview')) {
      data = { ok: true, issues: [], language: 'en-IN', token_estimate: 250, script_characters: 150, section_count: 5 };
    } else if (path.endsWith('/business-brain/draft') && method === 'PUT') {
      const body = request.postDataJSON();
      expect(body.expected_revision).toBe(state.revision);
      state.writes.push(body);
      state.sections = body.sections;
      state.revision = `draft-${state.writes.length + 1}`;
      data = { ok: true, revision: state.revision };
    } else if (path.endsWith('/business-brain/publish')) {
      expect(request.postDataJSON().expected_revision).toBe(state.revision);
      state.publishes++;
      status = failPublish ? 503 : 200;
      data = failPublish ? { detail: 'Publishing unavailable' } : { ok: true, compiled_version: 'cb_verified_test' };
    } else if (path === `/api/agents/${agent.id}`) data = { agent };
    else if (path.endsWith('/telephony-profile')) data = { profile: {}, afterHoursActions: [] };
    else if (path.endsWith('/billing/wallet')) data = { balanceUsd: 100 };
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.addInitScript(({ token, user }) => {
    sessionStorage.setItem('voxly_auth_token', token);
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('voxly_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    for (const key of ['voxly_tour_completed', 'voxly_tour_completed_default', 'voxly_tour_completed_script-test@example.invalid', 'dialtact_tour_completed_default']) localStorage.setItem(key, 'true');
  }, { token, user });
  await page.goto(`/#dashboard/employees?step=script&agent=${agent.id}`);
  const technicalDetails = page.getByRole('button', { name: 'Show technical details' });
  await Promise.race([
    page.getByRole('combobox', { name: 'Calling script' }).waitFor(),
    technicalDetails.waitFor(),
  ]);
  if (await technicalDetails.isVisible()) {
    await technicalDetails.click();
    throw new Error(`Workspace failed to render: ${await page.locator('body').innerText()}`);
  }
  await expect(page.getByRole('combobox', { name: 'Calling script' })).toBeVisible();
  return state;
}

test('incomplete generation asks for business review without technical diagnostics', async ({ page }) => {
  await setup(page, { generationReport: { status: 'degraded', provenance: { provider: 'gemini', model: 'test-generation-model', fallback: true }, issues: [{ code: 'deterministic_fallback', message: 'Model interpretation was unavailable; review the script.' }] } });
  const notice = page.getByTestId('agent-script-generation-status');
  await expect(notice).toContainText('Review the business details');
  await expect(notice).not.toContainText('Gemini');
  await expect(notice).not.toContainText('test-generation-model');
  await page.getByRole('combobox', { name: 'Calling script' }).fill(original + '\nEdited draft.');
  await expect(notice).toContainText('current draft has edits');
});

test('voice refresh preserves unsaved script; technical draft controls stay hidden', async ({ page }) => {
  const state = await setup(page);
  const editor = page.getByRole('combobox', { name: 'Calling script' });
  await expect(editor).toHaveValue(original);
  const edited = original + '\nTenant edited instruction.';
  await editor.fill(edited);
  const reads = state.reads;
  const voiceReads = state.voiceReads;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => state.voiceReads).toBeGreaterThan(voiceReads);
  await expect(editor).toHaveValue(edited);
  expect(state.reads).toBe(reads);
  await expect(page.getByTestId('review-script-btn')).toHaveCount(0);
  await expect(page.getByTestId('script-review-result')).toHaveCount(0);
  await expect(page.getByTestId('script-save-status')).toContainText('Unsaved changes');
  expect(state.writes).toHaveLength(0);
  expect(state.publishes).toBe(0);
  await editor.fill(edited + ' changed after review');
  await expect(page.getByTestId('script-review-result')).toHaveCount(0);
});

test('successful publication preserves extra facts, notes and guardrails', async ({ page }) => {
  const state = await setup(page);
  const editor = page.getByRole('combobox', { name: 'Calling script' });
  await expect(editor).toHaveValue(original);
  await editor.fill(original + '\nNew approved step.');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  await expect(page.getByTestId('script-review-result')).toHaveCount(0);
  await expect(page.getByTestId('script-published-version')).toHaveCount(0);
  await expect(page.getByTestId('agent-studio-unsaved')).toHaveCount(0);
  expect(state.publishes).toBe(1);
  const saved = state.writes[0].sections;
  expect(saved.find((row) => row.section_id === 'extra').raw_text).toBe('Escalate invoice disputes to finance.');
  expect(saved.find((row) => row.section_id === 'extra-facts').raw_text).toBe('Additional fact: support closes at 18:15.');
  expect(saved.find((row) => row.title === 'Identity & Purpose').raw_text).toContain('Preserve this identity note.');
  expect(saved.find((row) => row.title === 'Guardrails').raw_text).toContain('Never promise refunds without approval.');
  expect(saved.find((row) => row.title === 'FAQ & Objections').raw_text).toContain('Unstructured approved FAQ note: escalation requires consent.');
  expect(saved.filter((row) => ['saas_voice_config', 'Voice profile (console)'].includes(row.title)).every((row) => row.enabled === false)).toBe(true);
});

test('publish failure keeps unsaved draft and shows error', async ({ page }) => {
  const state = await setup(page, { failPublish: true });
  const editor = page.getByRole('combobox', { name: 'Calling script' });
  await expect(editor).toHaveValue(original);
  const edited = original + '\nKeep this edit after error.';
  await editor.fill(edited);
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-save-error')).toBeVisible();
  await expect(editor).toHaveValue(edited);
  await expect(page.getByTestId('agent-studio-unsaved')).toBeVisible();
  await expect(page.getByTestId('script-save-status')).toContainText('Unsaved changes');
  expect(state.publishes).toBe(1);
});

test('failed initial load blocks saving and retry restores the editor', async ({ page }) => {
  const state = await setup(page, { failRead: true });
  const editor = page.getByRole('combobox', { name: 'Calling script' });
  await expect(page.getByTestId('retry-script-load')).toBeVisible();
  await expect(editor).toBeDisabled();
  await expect(page.getByTestId('agent-save')).toBeDisabled();
  state.failRead = false;
  await page.getByTestId('retry-script-load').click();
  await expect(editor).toBeEnabled();
  await expect(editor).toHaveValue(original);
});

test('blank objection rule blocks saving; template stays factual and language aware', async ({ page }) => {
  const state = await setup(page);
  await page.getByTestId('add-objection-btn').click();
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-save-error')).toContainText('Complete the concern and response');
  expect(state.writes).toHaveLength(0);
  await page.getByTestId('remove-objection-0').click();
  await page.getByTestId('preset-objection-trust').click();
  await expect(page.getByTestId('objection-response-0')).toHaveValue('Yes, I am an AI assistant representing this business. What would you like to know?');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  const faq = state.writes[0].sections.find((row) => row.title === 'FAQ & Objections').raw_text;
  expect(faq).toContain('selected call language');
  expect(faq).not.toContain('recently engaged');
});

test('published script test opens the real call dialog, unsaved draft blocks testing', async ({ page }) => {
  await setup(page);
  await expect(page.getByRole('button', { name: 'Test published script' })).toBeEnabled();
  await page.getByRole('combobox', { name: 'Calling script' }).fill(original + '\nUnpublished change.');
  await expect(page.getByRole('button', { name: 'Test published script' })).toBeDisabled();
  await expect(page.getByTestId('agent-test-call')).toBeDisabled();
  await page.getByTestId('agent-studio-discard').click();
  await page.getByRole('button', { name: 'Test published script' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
});
