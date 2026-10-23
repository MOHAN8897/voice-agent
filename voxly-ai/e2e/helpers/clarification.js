import { expect } from '@playwright/test';

export async function setupClarification(page, { failAnalysis = false, failBuild = false } = {}) {
  const state = { analyses: [], builds: [], agents: [], failAnalysis, failBuild };
  const user = { id: 'clarification-user', userId: 'clarification-user', fullName: 'Flow Tester', email: 'clarification@example.invalid', hasCompletedOnboarding: true, role: 'subscriber', tenantId: 'clarification-workspace' };
  const agent = { id: 'clarified-agent', agent_id: 'clarified-agent', name: 'Meera', status: 'active', languages: ['en-IN'] };
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data = { ok: true, items: [] }, status = 200;
    if (path === '/api/auth/me') data = { user, tenant: { tenantId: user.tenantId }, role: 'subscriber' };
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: state.agents };
    else if (path.endsWith('/agents/languages')) data = { languages: [{ code: 'en-IN', name: 'English' }], default: 'en-IN' };
    else if (path.endsWith('/agents/analyze-brief')) {
      const body = route.request().postDataJSON();
      state.analyses.push(body);
      if (state.failAnalysis) { status = 503; data = { detail: { error: { code: 'brief_analysis_unavailable', message: 'We could not check the brief. Please try again.' } } }; }
      else if (!body.clarificationAnswers?.some((item) => item.field === 'agent_name')) data = { ok: true, status: 'needs_user_input', questions: [
        { field: 'agent_name', question: 'What name should your agent use?', reason: 'We need the speaker’s name for the introduction.', required: true },
        { field: 'offer', question: 'What is the offer, price and delivery format?', reason: 'The agent needs the exact offer before describing it.', required: true },
        { field: 'refund_policy', question: 'What is your refund policy?', reason: 'We will avoid guessing if this is unknown.', required: false },
      ] };
      else if (!body.clarificationAnswers.some((item) => item.field === 'next_step')) data = { ok: true, status: 'needs_user_input', questions: [
        { field: 'next_step', question: 'What should an interested caller do next?', reason: 'Your answer describes the offer but no next step.', required: true },
      ] };
      else data = { ok: true, status: 'ready', questions: [] };
    } else if (path.endsWith('/agents/build-employee')) {
      state.builds.push(route.request().postDataJSON());
      if (state.failBuild) { status = 502; data = { detail: { error: { code: 'script_compile_failed', message: 'Script generation failed. Please try again.' } } }; }
      else { state.agents = [agent]; data = { ok: true, agent, agentId: agent.id, script: '--- AGENT IDENTITY ---\nYou are Meera.\n\n--- CANONICAL OPENING ---\nHello, I’m Meera from Example.\n\n--- COMPANY & OFFER ---\nAn online course costs INR 500.' }; }
    } else if (path.endsWith('/business-brain')) data = { draft: { revision: 'draft-test', sections: [{ section_id: 'script', title: 'Calling script', type: 'facts', enabled: true, order: 20, raw_text: '--- AGENT IDENTITY ---\nYou are Meera.\n\n--- COMPANY & OFFER ---\nAn online course costs INR 500.' }] }, published: { version_id: 'private-version-must-not-display', optimizer_report: { status: 'ready', provenance: { provider: 'private-provider', model: 'private-model' } } } };
    else if (path.endsWith('/voice-options')) data = { voices: [], languages: [{ code: 'en-IN', label: 'English' }] };
    else if (path.endsWith('/billing/wallet')) data = { balanceUsd: 100 };
    else if (path.includes('/telephony-profile')) data = { profile: {}, afterHoursActions: [] };
    else if (path === `/api/agents/${agent.id}`) data = { agent };
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.addInitScript(({ user, token }) => {
    sessionStorage.setItem('voxly_auth_token', token);
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('voxly_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    for (const key of ['voxly_tour_completed', 'voxly_tour_completed_default', 'voxly_tour_completed_clarification@example.invalid', 'dialtact_tour_completed_default']) localStorage.setItem(key, 'true');
  }, { user, token });
  await page.goto('/#dashboard/employees');
  await page.getByRole('button', { name: /create ai employee/i }).first().click();
  await expect(page.getByTestId('create-employee-modal')).toBeVisible();
  return state;
}
