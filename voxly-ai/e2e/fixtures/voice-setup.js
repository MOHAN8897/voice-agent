export function voiceSetupData() {
  const user = { userId: 'voice-setup-user', id: 'voice-setup-user', fullName: 'Voice Tester', email: 'voice-setup@example.invalid', hasCompletedOnboarding: true, tenantId: 'voice-setup-workspace' };
  const b64 = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.userId, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  const profiles = ['low', 'medium', 'premium', 'custom_voice'].map((tier, index) => ({
    tier, label: tier, ready: true, profileRevision: index + 2,
    retailRate: { complete: true, usdMicrosPerMin: 10000, inrPaisePerMin: 100, fxRateInr: 100, version: 1 },
    engines: [{ id: `engine-${tier}`, label: 'Voice engine', models: [{ id: `model-${tier}`, label: 'Speech model', voices: [
      { id: `voice-${tier}`, label: 'Voice one', languages: ['te-IN'], gender: 'female' },
    ] }] }],
  }));
  const agent = { id: 'voice-setup-agent', agent_id: 'voice-setup-agent', name: 'Hima', languages: ['te-IN'], status: 'active', defaultTier: 'medium', voiceRevision: 1,
    active_compiled_brain_version: 'published', voiceSettings: { stackSelectionVersion: 1, profileRevision: 3, engineId: 'engine-medium', modelId: 'model-medium', voiceId: 'voice-medium' } };
  return { user, token, profiles, agent };
}

export async function setupVoiceWorkspace(page, { staleSelection = false, failSave = false, catalogVoices = 0 } = {}) {
  const data = voiceSetupData();
  if (staleSelection) data.agent.voiceSettings.profileRevision = 1;
  if (catalogVoices) data.profiles[0].engines[0].models[0].voices = Array.from({ length: catalogVoices }, (_, index) => ({
    id: `voice-low-${index + 1}`, label: `Voice ${index + 1}`, languages: ['te-IN'],
    category: index % 2 ? 'Conversational' : 'Normal', gender: index % 2 ? 'female' : 'male',
  }));
  const state = { ...data, writes: [] };
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let body = { ok: true, items: [] }, status = 200;
    if (path === '/api/auth/me') body = { user: state.user, tenant: { tenantId: state.user.tenantId }, role: 'owner' };
    else if (path === '/api/auth/session') body = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') body = { agents: [state.agent] };
    else if (path === '/api/voice-stacks/catalog') body = { profiles: state.profiles };
    else if (path.includes('/voice-options')) body = { voices: [], languages: [{ code: 'te-IN', label: 'Telugu' }] };
    else if (path.endsWith('/billing/wallet')) body = { balanceUsd: 100 };
    else if (path.endsWith('/business-brain')) body = { draft: { revision: 'draft-1', sections: [{ section_id: 'script', type: 'facts', title: 'Calling script', raw_text: 'Hello, I am Hima. How can I help?', enabled: true, order: 20 }] }, published: { version_id: 'published' } };
    else if (path.endsWith('/telephony-profile')) body = { profile: {} };
    else if (path === `/api/agents/${state.agent.id}`) {
      if (request.method() === 'PATCH') {
        const write = request.postDataJSON(); state.writes.push(write);
        if (failSave) { status = 409; body = { detail: { error: { code: 'profile_revision_conflict', message: 'Voice choices changed. Refresh and choose again.' } } }; }
        else state.agent = { ...state.agent, defaultTier: write.defaultTier, voiceSettings: write.voiceSettings, voiceRevision: state.agent.voiceRevision + 1 };
      }
      if (!failSave || request.method() !== 'PATCH') body = { agent: state.agent };
    }
    await route.fulfill({ status, json: body });
  });
  await page.addInitScript(({ user, token }) => {
    sessionStorage.setItem('voxly_auth_token', token);
    localStorage.setItem('voxly_auth_session', JSON.stringify(user));
    localStorage.setItem('voxly_tour_completed_voice-setup@example.invalid', 'true');
  }, data);
  await page.goto(`/#dashboard/employees?step=voice&agent=${state.agent.id}`);
  return state;
}
