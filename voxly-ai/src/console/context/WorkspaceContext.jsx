import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { initialWallet, availableNumbersCatalog } from '../data/initialWorkspaceData';
import { api } from '../../services/api';
import { normalizeAgent, normalizePhoneNumber, normalizeWallet } from '../../services/apiNormalize';
import { isUuid } from '../../lib/voiceDisplay';
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
  /** Server-computed canonical status counts for the call history header. */
  const [callStats, setCallStats] = useState(null);
  const [leads, setLeads] = useState([]);
  /**
   * Leads owned by the currently selected agent, fetched with a server-side
   * `agentId` filter. Kept separate from `leads` (the whole-workspace pipeline)
   * so an agent workspace never renders another agent's pipeline, and never even
   * receives it. Re-fetched whenever the selection changes.
   */
  const [agentLeads, setAgentLeads] = useState([]);
  const [agentLeadsId, setAgentLeadsId] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [wallet, setWallet] = useState(initialWallet);
  const [availableCatalog, setAvailableCatalog] = useState(availableNumbersCatalog);
  const [isLoading, setIsLoading] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [syncPartialErrors, setSyncPartialErrors] = useState([]);
  const loadInflightRef = useRef(null);
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
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [selectedCallId, setSelectedCallId] = useState(null);
  const [selectedLeadId, setSelectedLeadId] = useState(null);

  // Modal / Drawer visibility controls
  const [isCreateAgentOpen, setIsCreateAgentOpen] = useState(false);
  const [isBuyNumberOpen, setIsBuyNumberOpen] = useState(false);
  const [buyNumberPreselectedAgent, setBuyNumberPreselectedAgent] = useState(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isDialerModalOpen, setIsDialerModalOpen] = useState(false);
  // Payment wall. `addFundsReason` explains why it was opened, e.g. before a call.
  const [isAddFundsOpen, setIsAddFundsOpen] = useState(false);
  const [addFundsReason, setAddFundsReason] = useState(null);

  const openAddFunds = useCallback((reason = null) => {
    setAddFundsReason(reason);
    setIsAddFundsOpen(true);
  }, []);

  const closeAddFunds = useCallback(() => {
    setIsAddFundsOpen(false);
    setAddFundsReason(null);
  }, []);

  /** True when the wallet is at or below the balance needed to make a billed call. */
  const canAffordCalls = useCallback(() => {
    const inr = Number(wallet?.balanceInr) || 0;
    const usd = Number(wallet?.balanceUsd) || 0;
    if (inr > 0) return true;
    if (usd > 0) return true;
    return false;
  }, [wallet]);

  /** Ask for money only when the wallet is actually short. */
  const requireFunds = useCallback(
    (reason) => {
      if (canAffordCalls()) return false;
      openAddFunds(reason);
      return true;
    },
    [canAffordCalls, openAddFunds]
  );

  // ----------------------------------------------------------------
  // Initial Sync from API Gateway
  // ----------------------------------------------------------------
  const loadWorkspaceData = useCallback(async () => {
    if (!api.getToken()) {
      return;
    }
    // Coalesce overlapping refreshes — StrictMode + auth events must not fan out
    // parallel wallet/agents/calls GETs against the SaaS API.
    if (loadInflightRef.current) {
      return loadInflightRef.current;
    }
    setIsLoading(true);
    setSyncError(null);
    setSyncPartialErrors([]);

    const capture = async (label, fn, fallback = []) => {
      try {
        return await fn();
      } catch (e) {
        const msg = `${label}: ${e.message || e}`;
        setSyncPartialErrors((prev) => (prev.includes(msg) ? prev : [...prev, msg]));
        return fallback;
      }
    };

    const run = (async () => {
    // Suppress logout during batch sync — one 401 must not wipe the session mid-flight.
    await api.withAuthPolicy({ logoutOn401: false }, async () => {
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
      // Every agent the server returns is shown, including ones provisioned on the
      // shared platform tenant for the demo account. No client-side filtering.
      normAgents = normAgents.map((a) => {
        const num = normNumbers.find((n) => n.assignedAgentId === a.id);
        return num ? { ...a, assignedNumber: num.number, numberId: num.id } : a;
      });

      const [fetchedCalls, fetchedLeads, fetchedCampaigns, fetchedWallet, fetchedCatalog, fetchedCallStats] =
        await Promise.all([
          capture('Calls', () => api.calls.list({ limit: 100, agentMap }), []),
          capture('Leads', () => api.leads.list(), []),
          capture('Campaigns', () => api.campaigns.list(), []),
          capture('Wallet', () => api.billing.getWallet(), null),
          capture('Number catalog', () => api.telephony.getCatalog(catalogCountry), []),
          capture('Call summary', () => api.calls.stats(), null),
        ]);

      setAgents(normAgents);
      if (normAgents.length > 0) {
        setSelectedAgentId((prev) =>
          prev && normAgents.some((a) => a.id === prev) ? prev : normAgents[0].id
        );
      } else {
        setSelectedAgentId(null);
      }
      setPhoneNumbers(normNumbers);
      setCalls(fetchedCalls || []);
      setCallStats(fetchedCallStats);
      setLeads(fetchedLeads || []);
      setCampaigns(fetchedCampaigns || []);
      if (fetchedWallet) setWallet(normalizeWallet(fetchedWallet, initialWallet));
      setAvailableCatalog(fetchedCatalog?.length ? fetchedCatalog : []);
    } catch (err) {
      setSyncError(err.message || 'Could not sync workspace from API');
      console.warn('Workspace sync error:', err);
    } finally {
      setIsLoading(false);
      loadInflightRef.current = null;
    }
    });
    })();
    loadInflightRef.current = run;
    return run;
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
    let debounceTimer = null;
    const scheduleSync = () => {
      if (!api.getToken()) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        loadWorkspaceData();
        syncTenantWorkspace();
      }, 120);
    };
    // Boot: AuthProvider fires voxly:session after refreshSession — do not also
    // kick an immediate load here or we race two syncs on every hard reload.
    scheduleSync();
    const onAuth = () => scheduleSync();
    const onLogout = () => {
      clearTimeout(debounceTimer);
      setAgents([]);
      setPhoneNumbers([]);
      setCalls([]);
      setCallStats(null);
      setLeads([]);
      setAgentLeads([]);
      setAgentLeadsId(null);
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
      setSelectedAgentId(null);
    };
    window.addEventListener('voxly:session', onAuth);
    window.addEventListener('voxly:logout', onLogout);
    return () => {
      clearTimeout(debounceTimer);
      window.removeEventListener('voxly:session', onAuth);
      window.removeEventListener('voxly:logout', onLogout);
    };
  }, [loadWorkspaceData, syncTenantWorkspace]);

  /**
   * Reload the selected agent's leads whenever the selection changes.
   *
   * This is the enforcement point for "one agent's data stays in its own
   * workspace": the filter is applied by the server, and `agentLeadsId` records
   * which agent the current `agentLeads` actually belong to so a slow response
   * for a previous agent cannot land in the new agent's workspace.
   */
  useEffect(() => {
    if (!api.getToken()) {
      setAgentLeads([]);
      setAgentLeadsId(null);
      return;
    }
    if (!selectedAgentId) {
      setAgentLeads([]);
      setAgentLeadsId(null);
      return;
    }
    let cancelled = false;
    api.leads
      .list({ agentId: selectedAgentId })
      .then((rows) => {
        if (cancelled) return;
        setAgentLeads(rows);
        setAgentLeadsId(selectedAgentId);
      })
      .catch(() => {
        if (cancelled) return;
        setAgentLeads([]);
        setAgentLeadsId(selectedAgentId);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedAgentId]);

  /**
   * Leads for an agent workspace, or the whole pipeline when no agent is given.
   * Returns [] rather than falling back to another agent's rows — an empty board
   * is the honest answer for "this agent has no leads yet".
   */
  const leadsForAgent = useCallback(
    (agentId) => {
      if (!agentId) return leads;
      if (agentId === agentLeadsId) return agentLeads;
      // Selection changed but the scoped fetch has not landed yet. Falling back
      // to the workspace-wide list here would show the wrong agent's leads.
      return leads.filter((l) => l.agentId === agentId);
    },
    [agentLeads, agentLeadsId, leads]
  );

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
      if (newAgentData.numberId && isUuid(String(newAgentData.numberId))) {
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
          updates.boundaries?.length ||
          updates.variableDefinitions?.length
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

  // `nextStatus` is honoured when given — the card, settings panel and test panel
// each compute it from their own view, and deriving it again from this (possibly
// stale) `agents` array made them disagree.
  const toggleAgentStatus = async (agentId, nextStatus) => {
    const current = agents.find((a) => a.id === agentId);
    const target =
      nextStatus || (current?.status === 'active' ? 'paused' : 'active');
    if (!current || target === current.status) return target;
    // Optimistic, like toggleCampaignStatus: the card icon must flip on click,
    // not after a seven-endpoint workspace refetch.
    setAgents((prev) =>
      prev.map((a) =>
        a.id === agentId
          ? { ...a, status: target, updatedAt: new Date().toISOString() }
          : a
      )
    );
    try {
      if (authed()) {
        await api.agents.toggleStatus(agentId, target);
        return target;
      }
      return target;
    } catch (e) {
      // Roll back to what the server still believes, then surface the error.
      setAgents((prev) =>
        prev.map((a) => (a.id === agentId ? { ...a, status: current.status } : a))
      );
      if (authed()) throw e;
      console.warn('API toggleAgentStatus error:', e);
      return current.status;
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

  /**
   * Poll a purchase until the carrier order settles.
   *
   * A buy is a paid intent, not a live line: Telnyx provisioning is async and can
   * fail on out-of-account credit, in which case the wallet is refunded. Without
   * this the UI would report success for a number that never arrives.
   */
  const waitForPurchase = async (
    purchaseId,
    { attempts = 12, intervalMs = 1500, onFailed = null } = {}
  ) => {
    for (let i = 0; i < attempts; i += 1) {
      const purchase = await api.telephony.getPurchase(purchaseId).catch(() => null);
      if (!purchase) break;
      const status = String(purchase.status || '').toLowerCase();
      if (status === 'active') {
        await loadWorkspaceData();
        return { ...purchase, ok: true };
      }
      if (status === 'failed') {
        // The wallet was refunded server-side; re-read it so the balance the user
        // sees is the balance they actually have.
        await onFailed?.();
        return { ...purchase, ok: false, failureReason: purchase.lastError?.message || 'provision_failed' };
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return { purchaseId, status: 'pending', ok: false, failureReason: 'pending' };
  };

  const buyPhoneNumber = async (catalogItem, assignToAgentId = null) => {
    try {
      const provisioned = await api.telephony.buyNumber(catalogItem, assignToAgentId);
      // Only poll for carrier async provision. Inventory transfers already return a
      // phoneNumberId — stashing them leaves a forever "Provisioning…" banner.
      if (provisioned?.purchaseId && provisioned?.provisioning && !provisioned?.phoneNumberId) {
        stashPurchaseForRedirect(provisioned.purchaseId, assignToAgentId || null);
      }
      if (provisioned?.checkoutUrl || provisioned?.url) {
        window.location.href = provisioned.checkoutUrl || provisioned.url;
        return provisioned;
      }
      // Telnyx provisioning is async: the buy response is a paid purchase, not a
      // phone line. Only add to the pool once the server hands back a real
      // number id — otherwise a failed provision leaves a phantom line in the UI
      // and the agent gets bound to a number that does not exist.
      const phoneId = provisioned?.phoneNumberId || provisioned?.id;
      if (phoneId) {
        // Only a provisioned number is a line. Nothing else may enter the pool.
        setPhoneNumbers((prev) => [normalizePhoneNumber(provisioned, {}), ...prev]);
        setAvailableCatalog((prev) =>
          prev.filter((n) => n.formatted !== catalogItem.formatted)
        );
        if (assignToAgentId) {
          await assignNumberToAgent(phoneId, assignToAgentId);
        }
        return provisioned;
      }
      if (provisioned?.provisioning && provisioned?.purchaseId) {
        // The carrier order is async and can still fail (out of carrier credit, a
        // number that vanished). Poll for the terminal status so the caller can
        // report the real outcome instead of a hopeful success.
        const settled = await waitForPurchase(provisioned.purchaseId, {
          onFailed: refreshWallet,
        });
        return settled;
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
        if (!agentId) {
          await api.telephony.unassignNumber(numberId);
        } else {
          await api.telephony.assignNumber(numberId, agentId);
        }
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

  /**
   * Line-level routing toggles. Greeting, business hours and after-hours action are
   * agent-level settings and live on the telephony profile, not here.
   */
  const updateNumberRouting = async (numberId, routingUpdates) => {
    setPhoneNumbers((prev) =>
      prev.map((num) => (num.id === numberId ? { ...num, ...routingUpdates } : num))
    );

    try {
      const num = phoneNumbers.find((n) => n.id === numberId);
      await api.telephony.updateRouting(numberId, {
        ...routingUpdates,
        assignedAgentId: num?.assignedAgentId,
      });
      await loadWorkspaceData();
    } catch (e) {
      if (api.getToken()) {
        await loadWorkspaceData();
        throw e;
      }
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
    // Patch both caches: the workspace pipeline and the scoped agent board.
    const patch = (prev) =>
      prev.map((lead) => (lead.id === leadId ? { ...lead, stage: newStage } : lead));
    setLeads(patch);
    setAgentLeads(patch);

    try {
      await api.leads.updateStage(leadId, newStage);
    } catch (e) {
      if (authed()) throw e;
      console.warn('API updateLeadStage error:', e);
    }
  };

  const updateLeadNotes = async (leadId, notes) => {
    const patch = (prev) =>
      prev.map((lead) => (lead.id === leadId ? { ...lead, notes } : lead));
    setLeads(patch);
    setAgentLeads(patch);

    try {
      await api.leads.updateNotes(leadId, notes);
    } catch (e) {
      if (authed()) throw e;
      console.warn('API updateLeadNotes error:', e);
    }
  };

  const createLead = async (leadData) => {
    // A lead created inside an agent workspace belongs to that agent, or it would
    // vanish the moment the workspace switches to its scoped view.
    const withOwner = leadData.agentId
      ? leadData
      : { ...leadData, agentId: leadData.agentId === null ? null : selectedAgentId };
    const created = await api.leads.create(withOwner);
    setLeads((prev) => [created, ...prev]);
    if (created.agentId === agentLeadsId) {
      setAgentLeads((prev) => [created, ...prev]);
    }
    return created;
  };

  const placeOutboundCall = async ({ agentId, toE164, fromE164 } = {}) => {
    if (!agentId) throw new Error('Create a voice agent before placing outbound calls.');
    if (!toE164) throw new Error('Destination number is required.');
    const fromLine =
      fromE164 ||
      outboundFromE164 ||
      phoneNumbers.find((n) => n.assignedAgentId === agentId)?.number ||
      phoneNumbers[0]?.number ||
      null;
    const result = await api.calls.triggerOutbound({
      agentId,
      toE164,
      fromE164: fromLine,
    });
    await loadWorkspaceData();
    const callId = result.call_id || result.callId || result.id;
    if (callId) setSelectedCallId(callId);
    return result;
  };

  const triggerCallToLead = async (leadId) => {
    const lead = leads.find((l) => l.id === leadId);
    if (!lead) throw new Error('Lead not found');
    if (!lead.phone) throw new Error('Add a phone number to this lead before calling.');
    const agentId = lead.agentId || agents[0]?.id;
    return placeOutboundCall({ agentId, toE164: lead.phone });
  };

  // ----------------------------------------------------------------
  // Campaign Operations
  // ----------------------------------------------------------------
  const createCampaign = async (campaignData) => {
    const created = await api.campaigns.create(campaignData);
    // If backend did not handle contacts or legacy caller passed contacts without backend support:
    if (campaignData.contacts?.length && !created.totalContacts) {
      await api.campaigns.importContacts(created.id, campaignData.contacts);
    }
    if (campaignData.autoStart && created.status !== 'running') {
      try {
        await api.campaigns.start(created.id);
      } catch {
        /* already started or starting */
      }
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
    // Stripe removed — convert USD request to INR Razorpay order (legacy callers).
    const result = await api.billing.topUp(amountUsd);
    if (result?.orderId) {
      const { openRazorpayWalletCheckout } = await import('../../utils/razorpayCheckout');
      const cfg = await api.billing.razorpayConfig();
      await openRazorpayWalletCheckout({
        order: result,
        keyId: cfg?.keyId,
        user: null,
        onSuccess: async (response) => {
          await api.billing.verifyRazorpayPayment({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          await loadWorkspaceData();
        },
        onError: () => {},
      });
      return result;
    }
    await loadWorkspaceData();
    return result;
  };

  const refreshWallet = useCallback(async () => {
    if (!authed()) return;
    try {
      const fetchedWallet = await api.billing.getWallet();
      setWallet(normalizeWallet(fetchedWallet, initialWallet));
    } catch (e) {
      // Never let a background wallet refresh throw into a caller's flow — it
      // would be reported as a purchase failure the customer did not cause.
      console.warn('refreshWallet failed:', e?.message || e);
    }
  }, [authed]);

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
    callStats,
    leads,
    agentLeads,
    leadsForAgent,
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
    isAddFundsOpen,
    setIsAddFundsOpen,
    addFundsReason,
    openAddFunds,
    closeAddFunds,
    canAffordCalls,
    requireFunds,

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
    placeOutboundCall,
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
