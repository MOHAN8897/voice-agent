/** Map voice-agent API shapes → Voxly console UI models */

import { callStatus } from '../lib/callStatus';

export function normalizeAgent(row) {
  if (!row) return null;
  const id = row.agent_id || row.id || row.agentId;
  return {
    id,
    agent_id: id,
    name: row.name || 'Agent',
    status: row.status || 'active',
    role: row.role || 'Voice Agent',
    department: row.department || 'Operations',
    languages: row.languages || ['en-IN'],
    assignedNumber: row.assignedNumber || null,
    numberId: row.numberId || null,
    stats: row.stats || { totalCalls: 0, totalMinutes: 0, successRate: 100, avgDuration: '0m 00s' },
    updatedAt: row.updated_at || row.updatedAt || new Date().toISOString(),
  };
}

function countryFromE164(e164) {
  const n = String(e164 || '');
  if (n.startsWith('+1')) return 'US';
  if (n.startsWith('+44')) return 'GB';
  if (n.startsWith('+61')) return 'AU';
  if (n.startsWith('+91')) return 'IN';
  if (n.startsWith('+65')) return 'SG';
  if (n.startsWith('+353')) return 'IE';
  if (n.startsWith('+64')) return 'NZ';
  if (n.startsWith('+27')) return 'ZA';
  if (n.startsWith('+63')) return 'PH';
  return null;
}

export function normalizePhoneNumber(row, agentsById = {}) {
  if (!row) return null;
  const id = row.id || row.numberId;
  const e164 = row.e164 || row.number;
  const agentId = row.agentId || row.assignedAgentId;
  const agent = agentId ? agentsById[agentId] : null;
  const inferred = countryFromE164(e164);
  return {
    id,
    number: e164,
    formatted: row.formatted || e164,
    country: row.country || inferred || 'US',
    countryCode: row.countryCode || row.country || inferred || 'US',
    type: row.type || 'Local DID',
    assignedAgentId: agentId || null,
    assignedAgentName: agent?.name || (agentId ? 'Assigned' : 'Unassigned (Pool)'),
    // 0 means "price not supplied", which the UI renders as unknown rather than free.
monthlyCost: row.monthlyCost ?? row.monthlyUsd ?? 0,
    status: row.status || 'active',
    capabilities: row.capabilities || ['Voice'],
    usageMinutesThisMonth: row.usageMinutesThisMonth ?? 0,
    isDevSandbox: Boolean(row.isDevSandbox),
    label: row.label || null,
    // Line-level toggles. Greeting/hours live on the agent's telephony profile,
    // not here — see api.agents.getTelephonyProfile.
    inboundEnabled: row.inboundEnabled ?? true,
    outboundEnabled: row.outboundEnabled ?? true,
    billingSource: row.billingSource || null,
  };
}

export function normalizeWallet(apiWallet, fallback) {
  if (!apiWallet) return fallback;
  const fx = Number(apiWallet.fxRateInr) || 95.64;
  const inr = Number(apiWallet.balanceInr) || 0;
  let usd = Number(apiWallet.balanceUsd) || 0;
  // Razorpay top-ups land in INR only, so the dollar figure is derived here when
  // the server left cents empty. USD is the single displayed currency.
  if (usd <= 0 && inr > 0 && fx > 0) usd = inr / fx;
  const minutes =
    apiWallet.remainingMinutes != null
      ? Number(apiWallet.remainingMinutes)
      : Math.max(0, Math.floor(usd / Math.max(0.001, Number(apiWallet.rateUsdPerMin) || 0.12)));
  return {
    ...fallback,
    balanceUsd: usd,
    balanceInr: inr,
    usdEquivalent: usd,
    remainingMinutes: minutes,
    // Always USD in the console, whatever leg the wallet actually holds.
currency: 'USD',
    rateInrPerMin: apiWallet.rateInrPerMin,
    rateUsdPerMin: apiWallet.rateUsdPerMin,
    webRateInrPerMin: apiWallet.webRateInrPerMin,
    webRateUsdPerMin: apiWallet.webRateUsdPerMin,
    didMonthlyInr: apiWallet.didMonthlyInr,
    didMonthlyUsd: apiWallet.didMonthlyUsd,
    fxRateInr: fx,
    myUsageInr: apiWallet.myUsageInr,
    myUsageUsd: apiWallet.myUsageUsd,
  };
}

const LEAD_STAGE_TO_UI = {
  new: 'New',
  contacted: 'Contacted',
  qualified: 'Qualified',
  meeting_booked: 'Meeting Booked',
  unqualified: 'Unqualified',
};

const LEAD_STAGE_TO_API = {
  New: 'new',
  Contacted: 'contacted',
  Qualified: 'qualified',
  'Meeting Booked': 'meeting_booked',
  Unqualified: 'unqualified',
};

export function leadStageToApi(displayStage) {
  return LEAD_STAGE_TO_API[displayStage] || String(displayStage || 'new').toLowerCase().replace(/\s+/g, '_');
}

export function normalizeLead(row) {
  if (!row) return null;
  const id = row.leadId || row.id || row.lead_id;
  const rawStage = row.stage || 'new';
  const stage =
    LEAD_STAGE_TO_UI[rawStage] ||
    rawStage.charAt(0).toUpperCase() + rawStage.slice(1).replace(/_/g, ' ');
  return {
    id,
    leadId: id,
    // Which AI employee owns this lead. Null for hand-created workspace-level
    // leads. Must survive normalization — every per-agent filter keys off it.
    agentId: row.agentId || row.agent_id || null,
    name: row.name || 'Lead',
    phone: row.phone || '',
    email: row.email || '',
    company: row.company || '—',
    intent: row.intent || row.notes || 'Inbound',
    stage,
    notes: row.notes || '',
    createdAt: row.createdAt || row.created_at,
    updatedAt: row.updatedAt || row.updated_at,
  };
}

export function normalizeCall(row, agentsById = {}) {
  if (!row) return null;
  // Timeline rows carry call_id; a never-answered attempt carries attempt_id.
  const id = row.call_id || row.callId || row.id || row.attempt_id || row.attemptId;
  const agentId = row.agent_id || row.agentId;
  const agent = agentId ? agentsById[agentId] : null;
  const started = row.started_at || row.startedAt;
  const durationSec = row.duration_sec ?? row.durationSec ?? 0;
  const mins = Math.floor(durationSec / 60);
  const secs = durationSec % 60;
  const status = callStatus(row);
  const isAttempt = Boolean(row.is_attempt ?? row.isAttempt);
  return {
    id,
    callId: row.call_id || row.callId || id,
    attemptId: row.attempt_id || row.attemptId || null,
    isAttempt,
    connected: Boolean(row.connected ?? !isAttempt),
    direction: row.direction || 'inbound',
    channel: row.channel || 'pstn',
    status,
    inProgress: Boolean(row.in_progress ?? row.inProgress ?? status === 'in_progress'),
    agentId,
    agentName: agent?.name || row.agentName || (agentId ? 'Agent' : 'Unassigned'),
    customer: row.customer || null,
    callerName: row.customer || row.callerName || (row.caller_phone ? 'Caller' : '—'),
    callerPhone:
      row.caller_phone || row.callerPhone || row.to_e164 || row.from_number || row.fromNumber || null,
    calledPhone: row.called_phone || row.calledPhone || row.to_number || row.toNumber || null,
    startedAt: started,
    endedAt: row.ended_at || row.endedAt || null,
    duration: durationSec > 0 ? `${mins}m ${String(secs).padStart(2, '0')}s` : '—',
    outcome: row.disposition || row.summary || '—',
    disposition: row.disposition,
    summary: row.summary || null,
    policyReason: row.policy_reason || row.policyReason || null,
    costInr: row.cost_inr ?? row.costInr,
    costUsd: row.cost_usd ?? row.costUsd,
    endReason: row.end_reason || row.endReason,
    pipeline: row.pipeline,
    hasRecording: row.has_recording ?? row.hasRecording ?? false,
    hasTranscript: Boolean(row.has_transcript ?? row.hasTranscript),
    durationSec: durationSec || null,
  };
}

export function normalizeCampaign(row) {
  if (!row) return null;
  const id = row.campaignId || row.campaign_id || row.id;
  const retry = row.retryRules || row.retry_rules || {};
  return {
    id,
    campaignId: id,
    name: row.name || 'Campaign',
    status: row.status || 'draft',
    agentId: row.agentId || row.agent_id,
    concurrency: row.concurrency ?? 5,
    concurrencyLimit: row.concurrency ?? row.concurrencyLimit ?? 5,
    maxAttempts: retry.max_attempts ?? retry.maxAttempts ?? null,
    retryDelayMinutes: retry.retry_delay_minutes ?? retry.retryDelayMinutes ?? null,
    totalContacts: row.totalContacts ?? row.total_contacts ?? 0,
    objective: row.objective || '',
    callingHours: row.callingHours || '09:00 - 18:00',
  };
}

export function normalizeCatalogItem(item) {
  const e164 = item.e164 || item.phone_number || item.number;
  // No invented fallback: a missing price must surface as unknown, not as $5.
  const monthlyUsd = item.monthlyUsd ?? item.fee ?? (item.monthlyCents != null ? item.monthlyCents / 100 : null);
  return {
    e164,
    number: e164,
    formatted: item.formatted || e164,
    country: item.country || item.country_code || 'IN',
    type: item.type || 'Local DID',
    areaCode: item.areaCode || '',
    locality: item.locality || '',
    fee: monthlyUsd,
    monthlyUsd,
    features: item.features || ['Voice'],
  };
}
