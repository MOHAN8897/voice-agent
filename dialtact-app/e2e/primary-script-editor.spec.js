import { test, expect } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { writeFile } from 'node:fs/promises';

async function reticleVerify(page, commands, filename) {
  const bridge = '../artifacts/call-quality-review/callback-farewell-20261026/reticle_rpc.py';
  const { stdout } = await promisify(execFile)('python', [bridge, JSON.stringify(commands), page.url()], { timeout: 55_000 });
  await writeFile(`../artifacts/call-quality-review/callback-farewell-20261026/${filename}.jsonl`, stdout);
  const last = JSON.parse(stdout.trim().split('\n').at(-1));
  const evidence = JSON.parse(last.result.content.find((item) => item.type === 'text').text);
  expect(evidence.verdict?.verified ?? evidence.verified, JSON.stringify(evidence)).toBe('yes');
}

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

test('objectives publish, preserve multiline guidance and can be removed without returning on reload', async ({ page }) => {
  const state = await setup(page);
  await page.getByTestId('add-objective-btn').click();
  await expect(page.getByLabel('Rule 1 type')).toHaveValue('objective');
  await page.getByLabel('Rule 1 situation').fill('After the caller asks about a demo');
  await page.getByLabel('Rule 1 guidance').fill('Explain the approved service first.\nAsk for the preferred time, without promising availability.');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  const saved = state.writes.at(-1).sections;
  const metadata = JSON.parse(saved.find(row => row.title === 'saas_handling_rules').raw_text);
  expect(metadata.rules[0]).toMatchObject({kind:'objective',enabled:true,response:'Explain the approved service first.\nAsk for the preferred time, without promising availability.'});
  expect(saved.find(row => row.title === 'Objection & Objective Handling').raw_text).toContain('[Objective]');
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  await expect(page.getByLabel('Rule 1 guidance')).toContainText('Ask for the preferred time');
  await page.getByTestId('remove-objection-0').click();
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  await page.reload();
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  await expect(page.getByTestId('objection-rule-0')).toHaveCount(0);
  expect(state.publishes).toBe(2);
  expect(JSON.parse(state.writes.at(-1).sections.find(row => row.title === 'saas_handling_rules').raw_text).rules).toEqual([]);
  expect(state.writes.at(-1).sections.find(row => row.title === 'Objection & Objective Handling').raw_text).toContain('escalation requires consent');
});

async function setup(page, { failPublish = false, failRead = false, generationReport = null } = {}) {
  if (process.env.RETICLE_VERIFY) {
    // Capture only synthetic fixtures in this isolated browser context. The
    // developer's app keeps its normal network-body privacy setting.
    await page.route('**/src/services/reticleGate.js', async (route) => {
      const response = await route.fetch();
      const body = (await response.text()).replace('reticle.connect({', 'reticle.connect({ captureNetworkBodies: true,');
      await route.fulfill({ response, body });
    });
  }
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
    sessionStorage.setItem('dialtact_auth_token', token);
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    for (const key of ['dialtact_tour_completed', 'dialtact_tour_completed_default', 'dialtact_tour_completed_script-test@example.invalid', 'dialtact_tour_completed_default']) localStorage.setItem(key, 'true');
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
  // Hide only the development HUD: it otherwise intercepts app bottom controls.
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
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
  expect(saved.find((row) => row.title === 'Objection & Objective Handling').raw_text).toContain('Unstructured approved FAQ note: escalation requires consent.');
  expect(saved.filter((row) => ['saas_voice_config', 'Voice profile (console)'].includes(row.title)).every((row) => row.enabled === false)).toBe(true);
});

test('farewell after the script persists through publication and responsive layout', async ({ page }) => {
  const state = await setup(page);
  const farewell = page.getByTestId('agent-studio-farewell');
  const text = 'Thank you for giving us your time. We appreciate your interest. Goodbye.';
  if (process.env.RETICLE_VERIFY) {
    await reticleVerify(page, [
      { tool: 'reticle_act', args: { target: { testid: 'agent-studio-farewell' }, action: 'fill', args: { value: text } } },
      { tool: 'reticle_act_and_wait', args: { target: { testid: 'agent-save' }, action: 'click', until: { kind: 'allOf', predicates: [
        { kind: 'net', method: 'PUT', urlContains: '/business-brain/draft', status: 200, requestBodyContains: 'saas_call_end_policy' },
        { kind: 'net', method: 'POST', urlContains: '/business-brain/publish', status: 200 },
        { kind: 'text', contains: 'Saved for calls' },
      ] }, intent: 'Tenant farewell edits are persisted and published for subsequent calls.' } },
    ], 'reticle-farewell');
  } else {
    await farewell.fill(text);
    await page.getByTestId('agent-save').click();
  }
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  const config = state.writes[0].sections.find((row) => row.title === 'saas_call_end_policy');
  expect(config.enabled).toBe(false);
  expect(JSON.parse(config.raw_text).farewell).toBe(text);
  const script = await page.getByRole('combobox', { name: 'Calling script' }).boundingBox();
  const closing = await farewell.boundingBox();
  // Wide screens put the closing editor alongside the script; mobile keeps
  // the original top-to-bottom reading order.
  expect(closing.y > script.y || closing.x > script.x + script.width).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileScript = await page.getByRole('combobox', { name: 'Calling script' }).boundingBox();
  const mobileClosing = await farewell.boundingBox();
  expect(mobileClosing.y).toBeGreaterThan(mobileScript.y);
  await page.reload();
  await expect(farewell).toHaveValue(text);
  await expect(page.getByRole('combobox', { name: 'Calling script' })).toHaveValue(original);
});

test('callback requests stay visible on failure and clear after conversion', async ({ page }) => {
  await setup(page);
  let fail = true;
  let resolved = false;
  let dialCount = 0;
  let failDial = true;
  await page.route('**/api/calls/test-call/callback', async (route) => {
    dialCount++;
    expect(route.request().postDataJSON()).toMatchObject({ agentId: agent.id, mode: 'manual' });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: !failDial, status: failDial ? 'failed' : 'queued' }) });
  });
  await page.route('**/api/callback-requests**', async (route) => {
    if (route.request().method() === 'PATCH') {
      expect(route.request().postDataJSON().status).toBe('converted');
      if (!fail) resolved = true;
      await route.fulfill({ status: fail ? 503 : 200, contentType: 'application/json', body: JSON.stringify(fail ? { detail: 'Please retry saving.' } : { status: 'converted' }) });
    } else {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ requests: resolved ? [] : [{ id: 'test-callback', callId: 'test-call', agentId: agent.id, phone: '+12025550123', requestedWhen: 'Next month', requestText: 'Call me next month' }] }) });
    }
  });
  await page.goto('/#dashboard/leads');
  await expect(page.getByTestId('callback-request-list')).toContainText('Next month');
  expect(dialCount).toBe(0);
  await page.getByRole('button', { name: 'Call back', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Could not start the callback.');
  await expect(page.getByTestId('callback-request-list')).toContainText('Next month');
  failDial = false;
  await page.getByRole('button', { name: 'Call back', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Callback requested.' })).toBeVisible();
  expect(dialCount).toBe(2);
  await expect(page.getByTestId('callback-request-list')).toContainText('Next month');
  await page.getByRole('button', { name: 'Mark converted' }).click();
  await expect(page.getByRole('alert')).toContainText('Please retry saving.');
  await expect(page.getByTestId('callback-request-list')).toContainText('Next month');
  fail = false;
  if (process.env.RETICLE_VERIFY) {
    await reticleVerify(page, [{ tool: 'reticle_act_and_wait', args: { target: { role: 'button', name: 'Mark converted' }, action: 'click', until: { kind: 'allOf', predicates: [
      { kind: 'net', method: 'PATCH', urlContains: '/api/callback-requests/test-callback', status: 200, requestBodyContains: 'converted' },
      { kind: 'text', contains: 'No pending callback requests.' },
    ] }, intent: 'Converted callback requests leave the pending queue only after a successful save.' } }], 'reticle-callback');
  } else {
    await page.getByRole('button', { name: 'Mark converted' }).click();
  }
  await expect(page.getByRole('status').filter({ hasText: 'Marked converted' })).toBeVisible();
  await expect(page.getByText('No pending callback requests', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('No pending callback requests', { exact: true })).toBeVisible();
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
  await expect(page.getByTestId('agent-save')).toHaveCount(0);
  state.failRead = false;
  await page.getByTestId('retry-script-load').click();
  await expect(editor).toBeEnabled();
  await expect(editor).toHaveValue(original);
});

test('blank objection rule blocks saving; template stays factual and language aware', async ({ page }) => {
  const state = await setup(page);
  await page.getByTestId('add-objection-btn').click();
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('agent-save-error')).toContainText('Complete the situation and guidance');
  expect(state.writes).toHaveLength(0);
  await page.getByTestId('remove-objection-0').click();
  await page.getByTestId('preset-objection-trust').click();
  await expect(page.getByTestId('objection-response-0')).toHaveValue('Yes, I am an AI assistant representing this business. What would you like to know?');
  await page.getByTestId('agent-save').click();
  await expect(page.getByTestId('script-save-status')).toHaveText('Saved for calls');
  const faq = state.writes[0].sections.find((row) => row.title === 'Objection & Objective Handling').raw_text;
  expect(faq).toContain('selected call language');
  expect(faq).toContain('end_call means propose a close for server approval');
  expect(faq).toContain('future-interest or callback request is not a complete rejection');
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
