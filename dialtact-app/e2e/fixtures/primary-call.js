import { expect } from '@playwright/test';

export async function setupPrimaryCall(page, { phoneLines = true } = {}) {
  const user = { id: 'call-ui-user', userId: 'call-ui-user', fullName: 'Call Tester', name: 'Call Tester', email: 'call-ui@example.invalid', hasCompletedOnboarding: true, role: 'subscriber', tenantId: 'call-ui-tenant' };
  const b64 = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  const agent = { id: 'primary-call-agent', agent_id: 'primary-call-agent', name: 'Hima', status: 'active', languages: ['te-IN'], active_compiled_brain_version: 'published' };
  const state = { calls: [{ call_id: 'isolated-call', agent_id: agent.id, status: 'in_progress', direction: 'outbound', connected: true, duration_sec: 10, started_at: new Date().toISOString(), customer: 'Test conversation', has_recording: false, tenant_charge: { amount: 0.14, currency: 'USD' } }], filters: [], transcript: [{ role: 'assistant', text: 'Hello, how can I help?' }], recordings: [], dials: [] };
  const wav = Buffer.alloc(1644);
  wav.write('RIFF'); wav.writeUInt32LE(1636, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(1600, 40);
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    let data = { ok: true, items: [] };
    if (path === '/api/auth/me') data = { user, tenant: { tenantId: user.tenantId }, role: 'subscriber' };
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [agent] };
    else if (path === '/api/telephony/numbers') data = { numbers: phoneLines ? [{ id: 'owned-line', e164: '+12025550123', agentId: agent.id, status: 'active', outboundEnabled: true }] : [] };
    else if (path === '/api/calls') { state.filters.push(url.searchParams.get('status')); data = { calls: state.calls.filter(call => !url.searchParams.get('status') || call.status === url.searchParams.get('status')) }; }
    else if (path.endsWith('/transcript')) data = { lines: [...state.transcript], transcription: state.transcription || null };
    else if (path.endsWith('/audio-status')) data = { ready: state.calls[0].has_recording, source: state.calls[0].has_recording ? 'vobiz' : 'none' };
    else if (path.endsWith('/audio/mix')) { state.recordings.push(request.headers()); return route.fulfill({ contentType: 'audio/wav', body: wav }); }
    else if (path === '/api/billing/last-session') data = { has_call: true, duration_formatted: '1m 20s', tenant_wallet_deduction: { amount: 0.14, currency: 'USD' } };
    else if (path === '/api/billing/transactions') data = { transactions: [{ id: 'call-charge', kind: 'usage_pstn', amountCents: -14, amountInrPaise: 0, displayAmount: 0.14, displayCurrency: 'USD', referenceId: 'call:isolated-call', createdAt: new Date().toISOString(), description: 'Outbound Call (80s)', durationSec: 80 }] };
    else if (path.endsWith('/billing/wallet')) data = { balanceUsd: 100, remainingMinutes: 1000 };
    else if (path === '/api/calls/outbound') { state.dials.push(request.postDataJSON()); data = { ok: false, code: 'voice_preparation_failed', error: 'The agent could not get ready. No phone call was placed. Please try again.' }; }
    else if (path.endsWith('/business-brain')) data = { draft: { sections: [{ section_id: 'script', type: 'facts', title: 'Calling script', raw_text: 'Hello, how can I help?', enabled: true, order: 10 }] }, published: { version_id: 'published' } };
    else if (path.endsWith('/telephony-profile')) data = { profile: {} };
    else if (path === `/api/agents/${agent.id}`) data = { agent };
    await route.fulfill({ json: data });
  });
  await page.addInitScript(({ user, token }) => {
    for (const prefix of ['dialtact', 'dialtact']) {
      sessionStorage.setItem(`${prefix}_auth_token`, token);
      localStorage.setItem(`${prefix}_auth_session`, JSON.stringify(user));
      for (const suffix of ['', '_default', '_call-ui@example.invalid']) localStorage.setItem(`${prefix}_tour_completed${suffix}`, 'true');
    }
  }, { user, token });
  await page.goto('/#dashboard/calls');
  await page.addStyleTag({ content: '[data-reticle-overlay] { display:none !important }' });
  await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
  return state;
}
