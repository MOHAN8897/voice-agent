/**
 * Voxly AI — API client (voice agent backend, JWT + refresh)
 */
import { mockBackend } from './mockBackend';
import {
  normalizeAgent,
  normalizeCatalogItem,
  normalizeLead,
  normalizeCall,
  normalizeCampaign,
  leadStageToApi,
} from './apiNormalize';

const AUTH_TOKEN_KEY = 'voxly_auth_token';

function tokenStorage() {
  return typeof window !== 'undefined' ? window.sessionStorage : null;
}

function applyAuthResponse(data) {
  const access = data?.accessToken || data?.token;
  if (access) api.setToken(access);
}

const fetchOpts = { credentials: 'include' };

export function parseApiError(data, status) {
  const detail = data?.detail;
  const err =
    data?.error ||
    (detail && typeof detail === 'object' && (detail.error || detail)) ||
    null;
  const code = typeof err === 'object' ? err?.code : undefined;
  const message =
    (typeof err === 'object' && (err?.message || err?.code)) ||
    (typeof err === 'string' ? err : null) ||
    (typeof detail === 'string' ? detail : null) ||
    data?.message ||
    (status === 402
      ? 'Insufficient wallet credits. Add funds to continue.'
      : status === 429
        ? 'Too many requests. Wait a moment and try again.'
        : `HTTP ${status}`);
  const retryAfter = typeof err === 'object' ? err?.retry_after : undefined;
  const retryHint =
    status === 429 && retryAfter ? ` Retry in ${retryAfter}s.` : '';
  return { code, message: `${message}${retryHint}`, retryAfter, status };
}

function parseError(data, status) {
  return parseApiError(data, status).message;
}

export const api = {
  getBackendUrl() {
    if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL.replace(/\/$/, '');
    const stored = localStorage.getItem('voxly_backend_url');
    if (stored) return stored.replace(/\/$/, '');
    if (typeof window !== 'undefined') return `${window.location.origin}/api`;
    return 'http://localhost:8000/api';
  },

  getWsOrigin() {
    const api = this.getBackendUrl().replace(/\/$/, '');
    const http = api.replace(/\/api$/, '');
    return http.replace(/^http/, 'ws');
  },

  setBackendUrl(url) {
    if (!url) {
      localStorage.removeItem('voxly_backend_url');
      return;
    }
    const normalized = url.replace(/\/$/, '');
    const allowed =
      typeof window !== 'undefined' &&
      (normalized === window.location.origin ||
        normalized === `${window.location.origin}/api` ||
        /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/api)?$/i.test(normalized));
    if (!allowed) {
      throw new Error('Backend URL must be this site origin or localhost.');
    }
    localStorage.setItem('voxly_backend_url', normalized);
  },

  getToken() {
    const store = tokenStorage();
    return store?.getItem(AUTH_TOKEN_KEY) || null;
  },

  setToken(token) {
    const store = tokenStorage();
    if (!store) return;
    if (token) store.setItem(AUTH_TOKEN_KEY, token);
    else store.removeItem(AUTH_TOKEN_KEY);
  },

  clearToken() {
    const store = tokenStorage();
    store?.removeItem(AUTH_TOKEN_KEY);
  },

  async refreshAccessToken() {
    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const res = await fetch(`${backendUrl}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      ...fetchOpts,
      body: JSON.stringify({}),
    });
    if (!res.ok) return false;
    const data = await res.json();
    applyAuthResponse(data);
    return true;
  },

  async request(method, endpoint, body = null, customHeaders = {}, { allowMock = false } = {}) {
    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const token = this.getToken();
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const fullUrl = `${backendUrl}${path.replace(/^\/api/, '')}`;

    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...customHeaders,
    };

    const doFetch = async () =>
      fetch(fullUrl, {
        method,
        headers,
        ...fetchOpts,
        ...(body != null ? { body: JSON.stringify(body) } : {}),
      });

    let response = await doFetch();
    if (response.status === 401 && token) {
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        headers.Authorization = `Bearer ${this.getToken()}`;
        response = await doFetch();
      }
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      const isAuthRoute = path.includes('/auth/');
      const parsed = parseApiError(data, response.status);
      const fail = () => {
        const e = new Error(parsed.message);
        e.code = parsed.code;
        e.status = response.status;
        e.retryAfter = Number(response.headers.get('Retry-After') || parsed.retryAfter || 0);
        throw e;
      };
      if (backendUrl && !allowMock && !isAuthRoute) fail();
      if (!backendUrl || allowMock) {
        const mockResult = await mockBackend.handleRequest(method, endpoint, body, headers);
        if (mockResult.status >= 400) throw new Error(mockResult.data?.error || 'Request failed');
        return mockResult.data;
      }
      fail();
    }

    return data;
  },

  auth: {
    async login(email, password) {
      const data = await api.request('POST', '/api/auth/login', { email, password });
      applyAuthResponse(data);
      return data;
    },

    async signup(name, email, password) {
      const data = await api.request('POST', '/api/auth/signup', {
        email,
        password,
        fullName: name,
        orgName: `${name}'s Workspace`,
      });
      if (!data?.requiresEmailVerification) {
        applyAuthResponse(data);
      }
      return data;
    },

    async forgotPassword(email) {
      return await api.request('POST', '/api/auth/forgot-password', { email });
    },

    async resetPassword(token, newPassword) {
      return await api.request('POST', '/api/auth/reset-password', { token, newPassword });
    },

    async verifyEmail(token) {
      return await api.request('POST', '/api/auth/verify-email', { token });
    },

    async verifyEmailOtp(email, otp) {
      const data = await api.request('POST', '/api/auth/verify-email-otp', { email, otp });
      applyAuthResponse(data);
      return data;
    },

    async resendVerification(email) {
      return await api.request('POST', '/api/auth/resend-verification', { email });
    },

    async googleLogin(idToken) {
      const data = await api.request('POST', '/api/auth/google', { idToken });
      applyAuthResponse(data);
      return data;
    },

    async googleConfig() {
      return await api.request('GET', '/api/auth/google/config');
    },

    googleRedirectLogin() {
      const base = api.getBackendUrl().replace(/\/api\/?$/, '');
      window.location.href = `${base}/api/auth/google/start`;
    },

    async githubLogin() {
      throw new Error('GitHub sign-in is not enabled on this deployment.');
    },

    async getSession() {
      return await api.request('GET', '/api/auth/session');
    },

    async getMe() {
      return await api.request('GET', '/api/auth/me');
    },

    async logout() {
      const backendUrl = api.getBackendUrl().replace(/\/$/, '');
      const path = '/auth/logout';
      try {
        await fetch(`${backendUrl}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          credentials: 'include',
          body: JSON.stringify({}),
        });
      } catch {
        /* still clear local session */
      } finally {
        api.clearToken();
      }
      return { ok: true };
    },
  },

  agents: {
    async list() {
      const data = await api.request('GET', '/api/agents');
      const rows = data.agents || data;
      return Array.isArray(rows) ? rows.map(normalizeAgent) : [];
    },
    /**
     * Operational phone settings for one agent: greeting, business hours,
     * after-hours action, and the inbound/outbound toggles. Kept server-side and
     * separate from the Business Brain, which holds the AI's behaviour.
     */
    async getTelephonyProfile(agentId) {
      const data = await api.request('GET', `/api/agents/${agentId}/telephony-profile`);
      return {
        profile: data.profile || {},
        afterHoursActions: data.afterHoursActions || [],
      };
    },
    async saveTelephonyProfile(agentId, profile) {
      const data = await api.request('PUT', `/api/agents/${agentId}/telephony-profile`, profile);
      return data.profile || {};
    },
    /** What the live inbound path would decide right now, and why. */
    async getEffectiveTelephony(agentId) {
      return await api.request('GET', `/api/agents/${agentId}/telephony-profile/effective`);
    },
    async get(id) {
      const data = await api.request('GET', `/api/agents/${id}`);
      return normalizeAgent(data.agent || data);
    },
    async create(agentData) {
      const langs = agentData.languages || (agentData.language ? [agentData.language] : ['en-IN']);
      const data = await api.request('POST', '/api/agents', {
        name: agentData.name,
        languages: langs,
      });
      return normalizeAgent(data.agent || data);
    },
    async update(id, updates) {
      const data = await api.request('PATCH', `/api/agents/${id}`, {
        name: updates.name,
        status: updates.status,
        languages: updates.languages,
      });
      return normalizeAgent(data.agent || data);
    },
    async toggleStatus(id, status) {
      return api.agents.update(id, { status });
    },
    async duplicate(id) {
      const src = await api.agents.get(id);
      const copy = await api.agents.create({ name: `${src.name} (Copy)`, languages: src.languages });
      return copy;
    },
    async delete(id) {
      return await api.request('DELETE', `/api/agents/${id}`);
    },
    /**
     * Save an edited calling script back to the agent's published brain.
     * Only the script text changes; the compiler is not re-run, so the user's
     * wording is what the agent will say.
     */
    async saveCallingScript(agentId, script) {
      const data = await api.request('PUT', `/api/agents/${agentId}/business-brain/calling-script`, {
        script,
      });
      return data;
    },

    /**
     * Persist voice selection. Stored in the brain's voice config section, which
     * is what the live voice pipeline reads.
     */
    async saveVoice(agentId, { voiceId, speed, language }) {
      return await api.request('PUT', `/api/agents/${agentId}/business-brain/voice`, {
        voiceId,
        speed,
        language,
      });
    },

    /** The agent's stored brain: script, variables and voice config. */
    async getBusinessBrain(agentId) {
      const data = await api.request('GET', `/api/agents/${agentId}/business-brain`);
      const sections = data?.draft?.sections || [];
      const byTitle = (title) => sections.find((s) => s.title === title);
      const scriptSection =
        sections.find((s) => s.type === 'facts') || byTitle('Calling script') || null;
      const variablesSection = byTitle('saas_script_variables');
      const voiceSection = byTitle('saas_voice_config');
      let variables = [];
      let voice = {};
      try {
        if (variablesSection?.raw_text) {
          variables = JSON.parse(variablesSection.raw_text)?.variables || [];
        }
      } catch {
        variables = [];
      }
      try {
        if (voiceSection?.raw_text) voice = JSON.parse(voiceSection.raw_text) || {};
      } catch {
        voice = {};
      }
      return {
        callingScript: scriptSection?.raw_text || '',
        variables,
        voice,
        published: data?.published || null,
      };
    },

    async composeOnboarding(payload) {
      const data = await api.request('POST', '/api/app/agents/compose-onboarding', {
        name: payload.name,
        role: payload.role,
        language: payload.language,
        businessSummary: payload.businessSummary,
        goals: payload.goals,
        notes: payload.notes || '',
        brief: payload.brief || '',
        mode: payload.mode || 'instant_lead',
        industry: payload.industry || '',
        naturalSpokenStyle: Boolean(payload.naturalSpokenStyle),
      });
      return data;
    },
    async buildEmployee(payload) {
      const data = await api.request('POST', '/api/app/agents/build-employee', {
        brief: payload.brief,
        language: payload.language,
        mode: payload.mode || 'instant_lead',
        industry: payload.industry || '',
        naturalSpokenStyle: Boolean(payload.naturalSpokenStyle),
        employeeName: payload.employeeName || '',
      });
      const agent = data.agent || {};
      return {
        ...data,
        id: data.agentId || agent.agent_id || agent.id,
      };
    },
  },

  telephony: {
    async getNumbers() {
      const data = await api.request('GET', '/api/telephony/numbers');
      const rows = data.numbers || data;
      return Array.isArray(rows) ? rows : [];
    },
    async buyNumber(catalogItem, assignAgentId = null) {
      const e164 = catalogItem?.e164 || catalogItem?.phone_number || catalogItem;
      const body = {
        e164: typeof e164 === 'string' ? e164 : catalogItem?.e164,
        country: catalogItem?.country || catalogItem?.countryCode || 'IN',
        payMethod: catalogItem?.payMethod || 'wallet',
      };
      if (assignAgentId) body.assignAgentId = assignAgentId;
      return await api.request('POST', '/api/telephony/buy', body);
    },
    async assignNumber(numberId, agentId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/assign`, {
        agentId: agentId || null,
      });
    },
    async unassignNumber(numberId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/assign`, { agentId: null });
    },
    async releaseNumber(numberId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/release`);
    },
    async getPurchase(purchaseId) {
      return await api.request('GET', `/api/telephony/purchases/${purchaseId}`);
    },
    async updateRouting(numberId, routingConfig) {
      const body = {};
      if (routingConfig.agentId !== undefined) body.agentId = routingConfig.agentId;
      if (routingConfig.assignedAgentId !== undefined) body.agentId = routingConfig.assignedAgentId;
      if (routingConfig.inboundEnabled !== undefined) body.inboundEnabled = routingConfig.inboundEnabled;
      if (routingConfig.outboundEnabled !== undefined) body.outboundEnabled = routingConfig.outboundEnabled;
      if (routingConfig.inboundRouting?.action === 'ai_agent' && routingConfig.assignedAgentId) {
        body.agentId = routingConfig.assignedAgentId;
      }
      return await api.request('PUT', `/api/telephony/numbers/${numberId}/routing`, body);
    },
    async getVoiceOptions() {
      return await api.request('GET', '/api/telephony/voice-options');
    },
    async getCatalog(country = 'IN') {
      const data = await api.request('GET', `/api/telephony/numbers/search?country=${encodeURIComponent(country)}`);
      const rows = data.numbers || [];
      return rows.map((item) =>
        normalizeCatalogItem({
          ...item,
          country: item.country || item.country_code || country,
        })
      );
    },
  },

  calls: {
    /**
     * Call history. `status` uses the server's canonical vocabulary
     * (answered | missed | outbound | declined | failed | voicemail | in_progress)
     * and includes calls that never connected, so the Missed tab is real.
     */
    async list({ agentId, status, statuses, direction, limit = 100, offset = 0 } = {}) {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (offset) qs.set('offset', String(offset));
      if (agentId) qs.set('agentId', agentId);
      if (status) qs.set('status', status);
      if (statuses?.length) qs.set('status', statuses.join(','));
      if (direction) qs.set('direction', direction);
      const data = await api.request('GET', `/api/calls?${qs}`);
      const rows = data.calls || data;
      if (!Array.isArray(rows)) return [];
      const agents = await api.agents.list().catch(() => []);
      const agentMap = {};
      agents.forEach((a) => {
        agentMap[a.id] = a;
      });
      return rows.map((r) => normalizeCall(r, agentMap));
    },
    /** Counts and totals for the history header. */
    async stats({ agentId, since, until } = {}) {
      const qs = new URLSearchParams();
      if (agentId) qs.set('agentId', agentId);
      if (since) qs.set('since', since);
      if (until) qs.set('until', until);
      const suffix = qs.toString() ? `?${qs}` : '';
      return await api.request('GET', `/api/calls/stats${suffix}`);
    },
    async get(id) {
      return await api.request('GET', `/api/calls/${id}`);
    },
    async transcript(id) {
      return await api.request('GET', `/api/call/${id}/transcript`);
    },
    /** Structured post-call outcome: disposition, summary, extracted fields. */
    async outcome(id) {
      return await api.request('GET', `/api/call/${id}/outcome`);
    },
    async triggerOutbound({ agentId, toE164, fromE164 = null, dialRequestId = null }) {
      const body = { agentId, toE164 };
      if (fromE164) body.fromE164 = fromE164;
      if (dialRequestId) body.dialRequestId = dialRequestId;
      return await api.request('POST', '/api/calls/outbound', body);
    },
    /**
     * Call a missed caller back. Goes through the same outbound path as a manual
     * call, so every server-side guard still applies. Works for both a connected
     * call id and a ringing-attempt id.
     */
    async callback(callId, { toE164, agentId, fromE164, mode = 'manual' } = {}) {
      const body = { mode };
      if (toE164) body.toE164 = toE164;
      if (agentId) body.agentId = agentId;
      if (fromE164) body.fromE164 = fromE164;
      return await api.request('POST', `/api/calls/${callId}/callback`, body);
    },
    async listCallbacks(callId) {
      const data = await api.request('GET', `/api/calls/${callId}/callbacks`);
      return data.callbacks || [];
    },
  },

  leads: {
    async list() {
      const data = await api.request('GET', '/api/leads');
      const rows = data.leads || data;
      return Array.isArray(rows) ? rows.map(normalizeLead) : [];
    },
    async updateStage(leadId, stage) {
      return await api.request('PATCH', `/api/leads/${leadId}/stage`, {
        stage: leadStageToApi(stage),
      });
    },
    async updateNotes(leadId, notes) {
      return await api.request('PATCH', `/api/leads/${leadId}`, { notes });
    },
    async create(leadData) {
      const data = await api.request('POST', '/api/leads', {
        name: leadData.name,
        phone: leadData.phone,
        email: leadData.email,
        stage: leadStageToApi(leadData.stage || 'New'),
        notes: leadData.notes,
      });
      return normalizeLead(data.lead || data);
    },
  },

  campaigns: {
    async list() {
      const data = await api.request('GET', '/api/campaigns');
      const rows = data.campaigns || data;
      return Array.isArray(rows) ? rows.map(normalizeCampaign) : [];
    },
    async create(campaignData) {
      const data = await api.request('POST', '/api/campaigns', {
        name: campaignData.name,
        agentId: campaignData.agentId || campaignData.agent_id,
        concurrency: campaignData.concurrencyLimit || campaignData.concurrency || 5,
      });
      const row = data.campaign || data;
      return normalizeCampaign({
        ...row,
        name: row.name || campaignData.name,
        totalContacts: campaignData.totalContacts || 0,
        objective: campaignData.objective,
      });
    },
    async toggleStatus(id, currentStatus) {
      const next = currentStatus === 'running' ? 'paused' : 'running';
      await api.request('PATCH', `/api/campaigns/${id}/status`, { status: next });
      return next;
    },
    async start(id) {
      return await api.request('POST', `/api/campaigns/${id}/start`);
    },
    async importContacts(id, contacts) {
      return await api.request('POST', `/api/campaigns/${id}/contacts/import`, { contacts });
    },
    async analytics(id) {
      return await api.request('GET', `/api/campaigns/${id}/analytics`);
    },
  },

  billing: {
    async getWallet() {
      return await api.request('GET', '/api/billing/wallet');
    },
    /** Server-authoritative prices: number rental, top-up bounds, call rates. */
    async getCatalog() {
      return await api.request('GET', '/api/billing/catalog');
    },
    async topUp(amountUsd) {
      return await api.request('POST', '/api/billing/topup', { amountUsd });
    },
    async createRazorpayOrder(amountInr) {
      return await api.request('POST', '/api/billing/razorpay/create-order', { amountInr });
    },
    async verifyRazorpayPayment(payload) {
      return await api.request('POST', '/api/billing/razorpay/verify', payload);
    },
    async listInvoices() {
      const data = await api.request('GET', '/api/billing/invoices');
      return data.invoices || [];
    },
    async razorpayConfig() {
      return await api.request('GET', '/api/billing/razorpay/config');
    },
    async listTransactions(limit = 50, mine = false) {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (mine) qs.set('mine', 'true');
      const data = await api.request('GET', `/api/billing/transactions?${qs.toString()}`);
      return data.transactions || [];
    },
  },

  admin: {
    async overview() {
      return await api.request('GET', '/api/admin/overview');
    },
    async tenants() {
      const data = await api.request('GET', '/api/admin/tenants');
      return data.tenants || [];
    },
    async grantCredits({ tenantId, amountInrPaise, reason }) {
      return await api.request('POST', '/api/admin/credits', { tenantId, amountInrPaise, reason });
    },
  },

  brain: {
    async load(agentId) {
      return await api.request('GET', `/api/agents/${agentId}/business-brain`);
    },
    async saveDraft(agentId, sections) {
      return await api.request('PUT', `/api/agents/${agentId}/business-brain/draft`, { sections });
    },
    async publish(agentId) {
      return await api.request('POST', `/api/agents/${agentId}/business-brain/publish`);
    },
  },
};
