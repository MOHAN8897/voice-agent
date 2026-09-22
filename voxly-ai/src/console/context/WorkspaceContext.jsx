import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { initialWallet, availableNumbersCatalog } from '../data/initialWorkspaceData';
import { api } from '../../services/api';
import { normalizeAgent, normalizePhoneNumber, normalizeWallet } from '../../services/apiNormalize';
import { saveAndPublishAgentBrain } from '../../services/agentBrain';
import { stashPurchaseForRedirect } from '../ui/PurchaseProvisioningBanner';

function authed() {
  return !!api.getToken();
}

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({ children }) {
  const [agents, setAgents] = useState([]);
  const [phoneNumbers, setPhoneNumbers] = useState([]);
  const [calls, setCalls] = useState([]);
  const [leads, setLeads] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [wallet, setWallet] = useState(initialWallet);
  const [availableCatalog, setAvailableCatalog] = useState(availableNumbersCatalog);
  const [isLoading, setIsLoading] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [syncPartialErrors, setSyncPartialErrors] = useState([]);
  const [outboundFromE164, setOutboundFromE164] = useState(() => {
    if (typeof window === 'undefined') return '';
    return sessionStorage.getItem('voxly_outbound_from') || '';
  });
  const [catalogCountry, setCatalogCountry] = useState('IN');

  // Multiple Workspaces Management
  const defaultWorkspaces = [
    {
      id: 'ws-acme',
      name: 'Acme Health Corp',
      tier: 'Enterprise Fleet',
      role: 'Owner',
      activeAgents: 3,
      avatar: 'V'
    },
    {
      id: 'ws-summit',
      name: 'Summit Dental Care',
      tier: 'Professional Fleet',
      role: 'Admin',
      activeAgents: 2,
      avatar: 'S'
    },
    {
      id: 'ws-vance',
      name: 'Vance Capital Partners',
      tier: 'Scale Fleet',
      role: 'Billing Lead',
      activeAgents: 1,
      avatar: 'V'
    }
  ];

  const [workspaces, setWorkspaces] = useState(defaultWorkspaces);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState('ws-acme');
  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId) || workspaces[0];

  const switchWorkspace = (id) => {
    setCurrentWorkspaceId(id);
  };

  const createWorkspace = (name, tier = 'Starter Fleet') => {
    const newWs = {
      id: `ws-${Date.now()}`,
      name: name || 'New Organization',
      tier,
      role: 'Owner',
      activeAgents: 0,
      avatar: (name || 'N').charAt(0).toUpperCase()
    };
    setWorkspaces((prev) => [...prev, newWs]);
    setCurrentWorkspaceId(newWs.id);
    return newWs;
  };

  const [selectedPlan, setSelectedPlan] = useState('Professional');

  const updateWorkspaceTier = (tierName) => {
    const formattedTier = tierName.includes('Fleet') ? tierName : `${tierName} Fleet`;
    setSelectedPlan(tierName.replace(' Fleet', ''));
    setWorkspaces((prev) =>
      prev.map((w) =>
        w.id === currentWorkspaceId ? { ...w, tier: formattedTier } : w
      )
    );
  };

  // Active workspace navigation and selection states
  const [selectedAgentId, setSelectedAgentId] = useState('agent-maya');
  const [selectedCallId, setSelectedCallId] = useState(null);
  const [selectedLeadId, setSelectedLeadId] = useState(null);

  // Modal / Drawer visibility controls
  const [isCreateAgentOpen, setIsCreateAgentOpen] = useState(false);
  const [isBuyNumberOpen, setIsBuyNumberOpen] = useState(false);
  const [buyNumberPreselectedAgent, setBuyNumberPreselectedAgent] = useState(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isDialerModalOpen, setIsDialerModalOpen] = useState(false);

  // ----------------------------------------------------------------
  // Initial Sync from API Gateway
  // ----------------------------------------------------------------
  const loadWorkspaceData = useCallback(async () => {
    if (!api.getToken()) {
      return;
    }
    setIsLoading(true);
    setSyncError(null);
    setSyncPartialErrors([]);

    const capture = async (label, fn, fallback = []) => {
      try {
        return await fn();
      } catch (e) {
        setSyncPartialErrors((prev) => [...prev, `${label}: ${e.message || e}`]);
        return fallback;
      }
    };

    try {
      const fetchedAgents = await capture('Agents', () => api.agents.list(), []);
      const agentMap = {};
      let normAgents = (fetchedAgents || []).map((a) => {
        const n = normalizeAgent(a);
        agentMap[n.id] = n;
        return n;
      });

      const fetchedNumbers = await capture('Phone numbers', () => api.telephony.getNumbers(), []);
      const normNumbers = (fetchedNumbers || []).map((n) => normalizePhoneNumber(n, agentMap));
      normAgents = normAgents.map((a) => {
        const num = normNumbers.find((n) => n.assignedAgentId === a.id);
        return num ? { ...a, assignedNumber: num.number, numberId: num.id } : a;
      });

      const [fetchedCalls, fetchedLeads, fetchedCampaigns, fetchedWallet, fetchedCatalog] =
        await Promise.all([
          capture('Calls', () => api.calls.list(), []),
          capture('Leads', () => api.leads.list(), []),
          capture('Campaigns', () => api.campaigns.list(), []),
          capture('Wallet', () => api.billing.getWallet(), null),
          capture('Number catalog', () => api.telephony.getCatalog(catalogCountry), []),
        ]);

      setAgents(normAgents);
      setPhoneNumbers(normNumbers);
      setCalls(fetchedCalls || []);
      setLeads(fetchedLeads || []);
      setCampaigns(fetchedCampaigns || []);
      if (fetchedWallet) setWallet(normalizeWallet(fetchedWallet, initialWallet));
      setAvailableCatalog(fetchedCatalog?.length ? fetchedCatalog : []);
    } catch (err) {
      setSyncError(err.message || 'Could not sync workspace from API');
      console.warn('Workspace sync error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [catalogCountry]);

  const reloadCatalog = useCallback(
    async (country = catalogCountry) => {
      if (!api.getToken()) return;
      try {
        const fetched = await api.telephony.getCatalog(country);
        setAvailableCatalog(fetched?.length ? fetched : []);
        setCatalogCountry(country);
      } catch (e) {
        setSyncPartialErrors((prev) => [...prev, `Number catalog: ${e.message || e}`]);
        throw e;
      }
    },
    [catalogCountry]
  );

  const setPreferredOutboundFrom = useCallback((e164) => {
    setOutboundFromE164(e164 || '');
    if (typeof window !== 'undefined') {
      if (e164) sessionStorage.setItem('voxly_outbound_from', e164);
      else sessionStorage.removeItem('voxly_outbound_from');
    }
  }, []);

  const syncTenantWorkspace = useCallback(async () => {
    if (!api.getToken()) return;
    try {
      const me = await api.auth.getMe();
      const tenant = me?.tenant;
      if (tenant?.tenantId) {
        const name = tenant.name || 'My workspace';
        setWorkspaces([
          {
            id: tenant.tenantId,
            name,
            tier: 'Professional Fleet',
            role: 'Owner',
            activeAgents: 0,
            avatar: name.charAt(0).toUpperCase(),
          },
        ]);
        setCurrentWorkspaceId(tenant.tenantId);
      }
    } catch {
      /* keep existing */
    }
  }, []);

  useEffect(() => {
    if (!api.getToken()) return;
    setWorkspaces((prev) =>
      prev.map((w) =>
        w.id === currentWorkspaceId ? { ...w, activeAgents: agents.length } : w
      )
    );
  }, [agents.length, currentWorkspaceId]);

  useEffect(() => {
    loadWorkspaceData();
    syncTenantWorkspace();
    const onAuth = () => {
      loadWorkspaceData();
      syncTenantWorkspace();
    };
    const onLogout = () => {
      setAgents([]);
      setPhoneNumbers([]);
      setCalls([]);
      setLeads([]);
      setCampaigns([]);
      setWallet(initialWallet);
      setAvailableCatalog([]);
      setSyncError(null);
      setSyncPartialErrors([]);
      setWorkspaces([
        {
          id: 'ws-signed-out',
          name: 'Sign in to load workspace',
          tier: '—',
          role: '—',
          activeAgents: 0,
          avatar: '?',
        },
      ]);
      setCurrentWorkspaceId('ws-signed-out');
    };
    window.addEventListener('voxly:session', onAuth);
    window.addEventListener('voxly:logout', onLogout);
    return () => {
      window.removeEventListener('voxly:session', onAuth);
      window.removeEventListener('voxly:logout', onLogout);
    };
  }, [loadWorkspaceData, syncTenantWorkspace]);

  // ----------------------------------------------------------------
  // Agent Operations
  // ----------------------------------------------------------------
  const createAgent = async (newAgentData) => {
    try {
      const created = await api.agents.create(newAgentData);
      if (
        authed() &&
        (newAgentData.script ||
          newAgentData.greeting ||
          newAgentData.voice ||
          newAgentData.inboundRouting)
      ) {
        await saveAndPublishAgentBrain(created.id, newAgentData);
      }
      if (newAgentData.numberId) {
        await assignNumberToAgent(newAgentData.numberId, created.id, created.name);
      }
      await loadWorkspaceData();
      return created;
    } catch (e) {
      if (authed()) throw e;
      console.warn('API createAgent error, applying local fallback:', e);
      const id = `agent-${Date.now()}`;
      const localAgent = {
        ...newAgentData,
        id,
        status: 'active',
        stats: { totalCalls: 0, totalMinutes: 0, successRate: 100, avgDuration: '0m 00s' },
        updatedAt: new Date().toISOString()
      };
      setAgents((prev) => [localAgent, ...prev]);
      return localAgent;
    }
  };

  const updateAgent = async (agentId, updates) => {
    try {
      if (authed()) {
        await api.agents.update(agentId, {
          name: updates.name,
          status: updates.status,
          languages: updates.languages,
        });
        if (
          updates.script ||
          updates.greeting ||
          updates.voice ||
          updates.inboundRouting ||
          updates.boundaries?.length
        ) {
          await saveAndPublishAgentBrain(agentId, updates);
        }
        await loadWorkspaceData();
        return;
      }
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, ...updates, updatedAt: new Date().toISOString() } : a))
      );
    } catch (e) {
      if (authed()) {
        await loadWorkspaceData();
        throw e;
      }
      console.warn('API updateAgent error:', e);
    }
  };

  const duplicateAgent = async (agentId) => {
    try {
      const cloned = await api.agents.duplicate(agentId);
      setAgents((prev) => [cloned, ...prev]);
      return cloned;
    } catch (e) {
      if (api.getToken()) throw e;
      console.warn('API duplicateAgent error, falling back locally:', e);
      const source = agents.find((a) => a.id === agentId);
      if (!source) return;
      const localClone = {
        ...source,
        id: `agent-${Date.now()}`,
        name: `${source.name} (Copy)`,
        status: 'draft',
        assignedNumber: null,
        numberId: null,
        stats: { totalCalls: 0, totalMinutes: 0, successRate: 100, avgDuration: '0m 00s' },
        updatedAt: new Date().toISOString()
      };
      setAgents((prev) => [localClone, ...prev]);
      return localClone;
    }
  };

  const toggleAgentStatus = async (agentId) => {
    const current = agents.find((a) => a.id === agentId);
    const nextStatus = current?.status === 'active' ? 'paused' : 'active';
    try {
      if (authed()) {
        await api.agents.toggleStatus(agentId, nextStatus);
        await loadWorkspaceData();
        return;
      }
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, status: nextStatus, updatedAt: new Date().toISOString() } : a))
      );
    } catch (e) {
      if (authed()) {
        await loadWorkspaceData();
        throw e;
      }
      console.warn('API toggleAgentStatus error:', e);
    }
  };

  const deleteAgent = async (agentId) => {
    try {
      if (authed()) {
        await api.agents.delete(agentId);
        await loadWorkspaceData();
        return;
      }
      setAgents((prev) => prev.filter((a) => a.id !== agentId));
    } catch (e) {
      if (authed()) {
        await loadWorkspaceData();
        throw e;
      }
      console.warn('API deleteAgent error:', e);
    }
  };

  // ----------------------------------------------------------------
  // Virtual Number Operations
  // ----------------------------------------------------------------
  const buyPhoneNumber = async (catalogItem, assignToAgentId = null) => {
    try {
      const provisioned = await api.telephony.buyNumber(catalogItem, assignToAgentId);
      if (provisioned?.checkoutUrl || provisioned?.url) {
        stashPurchaseForRedirect(provisioned.purchaseId, assignToAgentId || null);
        window.location.href = provisioned.checkoutUrl || provisioned.url;
        return provisioned;
      }
      const norm = normalizePhoneNumber(provisioned, {});
      setPhoneNumbers((prev) => [norm, ...prev]);
      setAvailableCatalog((prev) => prev.filter((n) => n.formatted !== catalogItem.formatted));

      const phoneId = provisioned?.phoneNumberId || provisioned?.id;
      if (assignToAgentId && phoneId) {
        await assignNumberToAgent(phoneId, assignToAgentId);
      }
      return provisioned;
    } catch (e) {
      if (api.getToken()) throw e;
      console.warn('API buyPhoneNumber error, falling back locally:', e);
      const id = `num-${Date.now()}`;
      const agent = assignToAgentId ? agents.find((a) => a.id === assignToAgentId) : null;
      const localNumber = {
        id,
        number: catalogItem.number,
        formatted: catalogItem.formatted,
        country: catalogItem.country === 'US' ? 'United States' : catalogItem.country,
        countryCode: catalogItem.country,
        type: catalogItem.type,
        areaCode: catalogItem.areaCode,
        locality: catalogItem.locality,
        assignedAgentId: agent ? agent.id : null,
        assignedAgentName: agent ? agent.name : 'Unassigned (Pool)',
        monthlyCost: catalogItem.fee,
        status: 'active',
        capabilities: catalogItem.features || ['Voice'],
        usageMinutesThisMonth: 0,
        inboundRouting: {
          action: agent ? 'ai_agent' : 'voicemail',
          greetingPhrase: agent ? `Connecting you with ${agent.name}...` : 'Please leave a message.',
          businessHours: '08:00 - 18:00 (Local Time)',
          afterHoursAction: 'voicemail',
          recordingEnabled: true
        }
      };
      setPhoneNumbers((prev) => [localNumber, ...prev]);
      setAvailableCatalog((prev) => prev.filter((n) => n.formatted !== catalogItem.formatted));
      if (agent) {
        updateAgent(agent.id, { assignedNumber: catalogItem.number, numberId: id });
      }
      return localNumber;
    }
  };

  const assignNumberToAgent = async (numberId, agentId, agentName = '') => {
    try {
      if (authed()) {
        await api.telephony.assignNumber(numberId, agentId);
        await loadWorkspaceData();
        return;
      }
      const resolvedAgentName = agentName || (agents.find((a) => a.id === agentId)?.name ?? 'Agent');
      setPhoneNumbers((prev) =>
        prev.map((num) => {
          if (num.id === numberId) {
            return {
              ...num,
              assignedAgentId: agentId,
              assignedAgentName: resolvedAgentName,
              status: 'active',
              inboundRouting: { ...num.inboundRouting, action: 'ai_agent' },
            };
          }
          return num;
        })
      );
    } catch (e) {
      if (authed()) {
        await loadWorkspaceData();
        throw e;
      }
      throw e;
    }
  };

  const updateNumberRouting = async (numberId, routingUpdates) => {
    setPhoneNumbers((prev) =>
      prev.map((num) =>
        num.id === numberId ? { ...num, inboundRouting: { ...num.inboundRouting, ...routingUpdates } } : num
      )
    );

    try {
      const num = phoneNumbers.find((n) => n.id === numberId);
      await api.telephony.updateRouting(numberId, {
        ...routingUpdates,
        assignedAgentId: num?.assignedAgentId,
      });
    } catch (e) {
      if (api.getToken()) throw e;
      console.warn('API updateNumberRouting error:', e);
    }
  };

  const releasePhoneNumber = async (numberId) => {
    if (authed()) {
      await api.telephony.releaseNumber(numberId);
      await loadWorkspaceData();
      return;
    }
    const target = phoneNumbers.find((n) => n.id === numberId);
    if (target && target.assignedAgentId) {
      updateAgent(target.assignedAgentId, { assignedNumber: null, numberId: null });
    }
    setPhoneNumbers((prev) => prev.filter((n) => n.id !== numberId));
  };

  // ----------------------------------------------------------------
  // Lead Pipeline Operations
  // ----------------------------------------------------------------
  const updateLeadStage = async (leadId, newStage) => {
    setLeads((prev) =>
      prev.map((lead) => (lead.id === leadId ? { ...lead, stage: newStage } : lead))
    );

    try {
      await api.leads.updateStage(leadId, newStage);
    } catch (e) {
      if (authed()) throw e;
      console.warn('API updateLeadStage error:', e);
    }
  };

  const updateLeadNotes = async (leadId, notes) => {
    setLeads((prev) =>
      prev.map((lead) => (lead.id === leadId ? { ...lead, notes } : lead))
    );

    try {
      await api.leads.updateNotes(leadId, notes);
    } catch (e) {
      if (authed()) throw e;
      console.warn('API updateLeadNotes error:', e);
    }
  };

  const createLead = async (leadData) => {
    const created = await api.leads.create(leadData);
    setLeads((prev) => [created, ...prev]);
    return created;
  };

  const triggerCallToLead = async (leadId) => {
    const lead = leads.find((l) => l.id === leadId);
    if (!lead) throw new Error('Lead not found');
    if (!lead.phone) throw new Error('Add a phone number to this lead before calling.');
    const agentId = lead.agentId || agents[0]?.id;
    if (!agentId) throw new Error('Create a voice agent before placing outbound calls.');
    const fromLine =
      outboundFromE164 ||
      phoneNumbers.find((n) => n.assignedAgentId === agentId)?.number ||
      phoneNumbers[0]?.number ||
      null;
    const result = await api.calls.triggerOutbound({
      agentId,
      toE164: lead.phone,
      fromE164: fromLine,
    });
    await loadWorkspaceData();
    const callId = result.call_id || result.callId || result.id;
    if (callId) setSelectedCallId(callId);
    return result;
  };

  // ----------------------------------------------------------------
  // Campaign Operations
  // ----------------------------------------------------------------
  const createCampaign = async (campaignData) => {
    const created = await api.campaigns.create(campaignData);
    if (campaignData.contacts?.length) {
      await api.campaigns.importContacts(created.id, campaignData.contacts);
    }
    if (campaignData.autoStart) {
      await api.campaigns.start(created.id);
    }
    await loadWorkspaceData();
    return created;
  };

  const startCampaign = async (campaignId) => {
    await api.campaigns.start(campaignId);
    await loadWorkspaceData();
  };

  const importCampaignContacts = async (campaignId, contacts) => {
    await api.campaigns.importContacts(campaignId, contacts);
    await loadWorkspaceData();
  };

  const fetchCampaignAnalytics = async (campaignId) => api.campaigns.analytics(campaignId);

  const toggleCampaignStatus = async (campaignId) => {
    const current = campaigns.find((c) => c.id === campaignId);
    const optimistic = current?.status === 'running' ? 'paused' : 'running';
    setCampaigns((prev) =>
      prev.map((c) => (c.id === campaignId ? { ...c, status: optimistic } : c))
    );

    try {
      const next = await api.campaigns.toggleStatus(campaignId, current?.status || 'draft');
      setCampaigns((prev) => prev.map((c) => (c.id === campaignId ? { ...c, status: next } : c)));
    } catch (e) {
      if (authed()) {
        await loadWorkspaceData();
        throw e;
      }
      console.warn('API toggleCampaignStatus error:', e);
    }
  };

  // ----------------------------------------------------------------
  // Wallet Operations
  // ----------------------------------------------------------------
  const addFunds = async (amountUsd) => {
    const result = await api.billing.topUp(amountUsd);
    if (result?.checkoutUrl) {
      window.location.href = result.checkoutUrl;
      return result;
    }
    await loadWorkspaceData();
    return result;
  };

  const refreshWallet = async () => {
    if (!authed()) return;
    const fetchedWallet = await api.billing.getWallet();
    setWallet(normalizeWallet(fetchedWallet, initialWallet));
  };

  const toggleAutoRecharge = () => {
    setWallet((prev) => ({
      ...prev,
      autoRechargeEnabled: !prev.autoRechargeEnabled
    }));
  };

  const updateAutoRechargeSettings = (thresholdUsd, amountUsd) => {
    setWallet((prev) => ({
      ...prev,
      autoRechargeThresholdUsd: thresholdUsd,
      autoRechargeAmountUsd: amountUsd
    }));
  };

  const value = {
    // Data
    agents,
    phoneNumbers,
    calls,
    leads,
    campaigns,
    wallet,
    availableCatalog,
    isLoading,
    syncError,
    syncPartialErrors,
    loadWorkspaceData,

    // Workspaces
    workspaces,
    currentWorkspace,
    switchWorkspace,
    createWorkspace,
    selectedPlan,
    setSelectedPlan,
    updateWorkspaceTier,

    // Selections
    selectedAgentId,
    setSelectedAgentId,
    selectedAgent: agents.find((a) => a.id === selectedAgentId) || agents[0],
    selectedCallId,
    setSelectedCallId,
    selectedCall: calls.find((c) => c.id === selectedCallId) || null,
    selectedLeadId,
    setSelectedLeadId,
    selectedLead: leads.find((l) => l.id === selectedLeadId) || null,

    // Dialog & Flow States
    isCreateAgentOpen,
    setIsCreateAgentOpen,
    isBuyNumberOpen,
    setIsBuyNumberOpen,
    buyNumberPreselectedAgent,
    setBuyNumberPreselectedAgent,
    isCommandPaletteOpen,
    setIsCommandPaletteOpen,
    isDialerModalOpen,
    setIsDialerModalOpen,

    // Handlers
    createAgent,
    updateAgent,
    duplicateAgent,
    toggleAgentStatus,
    deleteAgent,
    buyPhoneNumber,
    assignNumberToAgent,
    updateNumberRouting,
    releasePhoneNumber,
    updateLeadStage,
    updateLeadNotes,
    createLead,
    triggerCallToLead,
    refreshWallet,
    reloadCatalog,
    catalogCountry,
    outboundFromE164,
    setPreferredOutboundFrom,
    startCampaign,
    importCampaignContacts,
    fetchCampaignAnalytics,
    createCampaign,
    toggleCampaignStatus,
    addFunds,
    toggleAutoRecharge,
    updateAutoRechargeSettings
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
}
