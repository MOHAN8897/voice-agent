/** Map voice-agent API shapes → Voxly console UI models */

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

export function normalizePhoneNumber(row, agentsById = {}) {
  if (!row) return null;
  const id = row.id || row.numberId;
  const e164 = row.e164 || row.number;
  const agentId = row.agentId || row.assignedAgentId;
  const agent = agentId ? agentsById[agentId] : null;
  return {
    id,
    number: e164,
    formatted: row.formatted || e164,
    country: row.country || 'IN',
    countryCode: row.countryCode || row.country || 'IN',
    type: row.type || 'Local DID',
    assignedAgentId: agentId || null,
    assignedAgentName: agent?.name || (agentId ? 'Assigned' : 'Unassigned (Pool)'),
    monthlyCost: row.monthlyCost ?? 5,
    status: row.status || 'active',
    capabilities: row.capabilities || ['Voice'],
    usageMinutesThisMonth: row.usageMinutesThisMonth ?? 0,
    inboundRouting: row.inboundRouting || {
      action: agentId ? 'ai_agent' : 'voicemail',
      greetingPhrase: 'Thank you for calling.',
      businessHours: '08:00 - 18:00',
      afterHoursAction: 'voicemail',
      recordingEnabled: true,
    },
  };
}

export function normalizeWallet(apiWallet, fallback) {
  if (!apiWallet) return fallback;
  const usd = apiWallet.balanceUsd ?? 0;
  const minutes = Math.max(0, Math.floor((usd / 0.095) * 60) / 60);
  return {
    ...fallback,
    balanceUsd: usd,
    balanceInr: apiWallet.balanceInr,
    usdEquivalent: usd,
    remainingMinutes: minutes,
    currency: apiWallet.currency || 'USD',
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
  const id = row.call_id || row.callId || row.id;
  const agentId = row.agent_id || row.agentId;
  const agent = agentId ? agentsById[agentId] : null;
  const started = row.started_at || row.startedAt;
  const durationSec = row.duration_sec ?? row.durationSec ?? 0;
  const mins = Math.floor(durationSec / 60);
  const secs = durationSec % 60;
  return {
    id,
    callId: id,
    direction: row.direction || 'inbound',
    channel: row.channel || 'pstn',
    agentId,
    agentName: agent?.name || row.agentName || 'Agent',
    callerName: row.customer || row.callerName || 'Caller',
    callerPhone: row.caller_phone || row.callerPhone || row.to_e164 || '—',
    startedAt: started,
    duration: `${mins}m ${String(secs).padStart(2, '0')}s`,
    outcome: row.disposition || row.summary || row.outcome || '—',
    disposition: row.disposition,
    summary: row.summary,
    hasRecording: row.has_recording ?? row.hasRecording ?? false,
  };
}

export function normalizeCampaign(row) {
  if (!row) return null;
  const id = row.campaignId || row.campaign_id || row.id;
  return {
    id,
    campaignId: id,
    name: row.name || 'Campaign',
    status: row.status || 'draft',
    agentId: row.agentId || row.agent_id,
    concurrency: row.concurrency ?? 5,
    totalContacts: row.totalContacts ?? row.total_contacts ?? 0,
    objective: row.objective || '',
    callingHours: row.callingHours || '09:00 - 18:00',
  };
}

export function normalizeCatalogItem(item) {
  const e164 = item.e164 || item.phone_number || item.number;
  return {
    e164,
    number: e164,
    formatted: item.formatted || e164,
    country: item.country || item.country_code || 'IN',
    type: item.type || 'Local DID',
    areaCode: item.areaCode || '',
    locality: item.locality || '',
    fee: item.fee ?? item.monthlyCents ? item.monthlyCents / 100 : 5,
    features: item.features || ['Voice'],
  };
}
