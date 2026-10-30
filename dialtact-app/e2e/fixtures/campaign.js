import { expect } from '@playwright/test';

export async function setupCampaign(page, { failCreate = false, initialCampaigns = [], analyticsStatus, analyticsDelay = 0, variableReport, lists = [], listContacts = [] } = {}) {
  const state = { campaigns: [...initialCampaigns], creates: [], validations: [], variableChecks: [], analyticsRequests: 0, analyticsActive: 0, analyticsPeak: 0 };
  const user = { id: 'campaign-audit-user', userId: 'campaign-audit-user', name: 'Campaign Tester', fullName: 'Campaign Tester', email: 'campaign-audit@example.invalid', hasCompletedOnboarding: true, role: 'subscriber', tenantId: 'campaign-audit-tenant' };
  const b64 = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
  const token = `${b64({ alg: 'none' })}.${b64({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test`;
  const agent = { id: 'campaign-agent', agent_id: 'campaign-agent', name: 'Customer Follow-up', status: 'active', languages: ['te-IN'] };
  await page.route('**/api/**', async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    let data = { ok: true, items: [] }, status = 200;
    if (path === '/api/auth/me') data = { user, tenant: { tenantId: user.tenantId }, role: 'subscriber' };
    else if (path === '/api/auth/session') data = { authenticated: true, saas_auth_enabled: true };
    else if (path === '/api/agents') data = { agents: [agent] };
    else if (path === '/api/campaigns' && request.method() === 'GET') data = { campaigns: state.campaigns };
    else if (path === '/api/campaigns' && request.method() === 'POST') {
      const body = request.postDataJSON(); state.creates.push(body);
      status = failCreate ? 503 : 200;
      data = failCreate ? { detail: { error: { message: 'Campaign storage unavailable' } } } : { ok: true, campaign: { ...body, id: 'isolated-campaign', campaignId: 'isolated-campaign', status: body.autoStart ? 'running' : 'draft', totalContacts: body.contacts.length } };
      if (!failCreate) state.campaigns.push(data.campaign);
    } else if (path.endsWith('/analytics')) {
      state.analyticsRequests += 1; state.analyticsActive += 1;
      state.analyticsPeak = Math.max(state.analyticsPeak, state.analyticsActive);
      if (analyticsDelay) await new Promise((resolve) => setTimeout(resolve, analyticsDelay));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: analyticsStatus, attempts: 0, connects: 0, dispositions: { pending: 121 } }) });
      state.analyticsActive -= 1;
      return;
    }
    else if (path === '/api/contacts/lists') data = { lists };
    else if (path.startsWith('/api/contacts/lists/') && path.endsWith('/contacts')) data = { contacts: listContacts, totalContacts: listContacts.length };
    else if (path === '/api/contacts/parse') {
      const body = request.postDataJSON();
      const rawText = body.rawText || Buffer.from(body.contentBase64.split(',').at(-1), 'base64').toString('utf8');
      const [header, ...lines] = rawText.trim().split('\n');
      const headers = header.split(',');
      const rows = lines.map((line) => Object.fromEntries(line.split(',').map((value, i) => [headers[i], value])));
      data = { ok: true, fileName: 'pasted.csv', totalRows: rows.length, rows, previewRows: rows.slice(0, 50), headers, detectedMappings: Object.fromEntries(headers.map((key) => [key, { field: key }])), warnings: [] };
    } else if (path === '/api/contacts/normalize-preview') {
      const body = request.postDataJSON(); state.validations.push(body);
      data = { ok: true, totalRows: body.rows.length, validCount: body.rows.length, invalidCount: 0, duplicateCount: 0, validContacts: body.rows, invalidContacts: [] };
    } else if (path === '/api/campaigns/validate-variables') {
      state.variableChecks.push(request.postDataJSON()); data = { ok: true, valid: true, missing_breakdown: {}, scriptVersion: 'cb_campaign_ui', ...variableReport };
    } else if (path.endsWith('/billing/wallet')) data = { balanceUsd: 100 };
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.addInitScript(({ user, token }) => {
    sessionStorage.setItem('dialtact_auth_token', token);
    sessionStorage.setItem('dialtact_auth_token', token);
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    localStorage.setItem('dialtact_auth_session', JSON.stringify(user));
    for (const key of ['dialtact_tour_completed', 'dialtact_tour_completed_default', 'dialtact_tour_completed_campaign-audit@example.invalid', 'dialtact_tour_completed_default']) localStorage.setItem(key, 'true');
  }, { user, token });
  await page.goto('/#dashboard/campaigns');
  // The development-only HUD overlaps product controls on narrow screens.
  // Production builds omit it; leave the SDK and product assertions enabled.
  await page.addStyleTag({ content: '[data-reticle-overlay] { display: none !important; }' });
  await expect(page.getByRole('button', { name: 'New campaign', exact: true })).toBeVisible();
  return state;
}
