import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Search,
  Volume2,
  Sparkles,
  FileText,
  RefreshCw,
  Filter,
  PhoneCall,
  PhoneIncoming,
  PhoneOutgoing,
  Voicemail,
  Play,
  Pause,
  Download,
  CreditCard,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import { PHONE_STACK_LABEL, bucketToApiStatus } from '../../lib/phoneLabels';
import {
  CALL_STATUS_TABS,
  callStatus,
  formatDuration,
  isCallbackCandidate,
  statusMeta,
} from '../../lib/callStatus';
import { callReference, endReasonLabel, pipelineLabel } from '../../lib/internalLabels';

const STATUS_ICON = {
  answered: PhoneIncoming,
  missed: PhoneIncoming,
  voicemail: Voicemail,
  outbound: PhoneOutgoing,
  declined: PhoneOutgoing,
  failed: PhoneOutgoing,
  in_progress: PhoneCall,
};

const TONE_CLASS = {
  success: 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]',
  warning: 'bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]',
  danger: 'bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]',
  info: 'bg-[#EEF2FF] text-[#4338CA] border-[#C7D2FE]',
  muted: 'bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]',
};

function StatusPill({ status, className = '' }) {
  const meta = statusMeta(status);
  const Icon = STATUS_ICON[status] || PhoneIncoming;
  return (
    <span
      title={meta.hint}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-bold uppercase tracking-wider ${
        TONE_CLASS[meta.tone] || TONE_CLASS.muted
      } ${className}`}
    >
      <Icon className="w-3 h-3" />
      {meta.short}
    </span>
  );
}

function RecordingPlayer({ call }) {
  const audioRef = React.useRef(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  // Internal carrier reasons and pipeline names are translated, never shown raw.
  const reasonLabel = endReasonLabel(call?.endReason);
  const voiceLabel = pipelineLabel(call?.pipeline);

  const src = useMemo(() => {
    if (!call?.connected) return null;
    // mix is the mixed-down conversation; the API serves wav/mp3 and sets
    // Accept-Ranges, so the browser can seek.
    return `${api.getBackendUrl().replace(/\/$/, '')}/call/${call.id}/audio/mix`;
  }, [call?.id, call?.connected]);

  useEffect(() => {
    setPlaying(false);
    setProgress(0);
  }, [call?.id]);

  const toggle = async () => {
    const el = audioRef.current;
    if (!el) return;
    if (!el.src) {
      setLoading(true);
      el.src = src;
      try {
        await el.play();
        setPlaying(true);
      } catch {
        showToast('Recording is not available yet', 'error');
      } finally {
        setLoading(false);
      }
      return;
    }
    if (el.paused) {
      try {
        await el.play();
        setPlaying(true);
      } catch {
        setPlaying(false);
      }
    } else {
      el.pause();
      setPlaying(false);
    }
  };

  const onTimeUpdate = () => {
    const el = audioRef.current;
    if (el && el.duration) setProgress((el.currentTime / el.duration) * 100);
  };

  if (!call.hasRecording) {
    return (
      <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-[#0F0E17]">
          <Volume2 className="w-3.5 h-3.5 text-[#8C879A]" />
          <span>Call recording</span>
        </div>
        <p className="text-[11px] text-[#8C879A]">
          {call.connected
            ? 'No recording for this call.'
            : 'Never connected, so there is no recording.'}
        </p>
      </div>
    );
  }

  return (
    <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2.5">
      <div className="flex items-center justify-between text-xs text-[#524E5E]">
        <span className="flex items-center gap-1.5 font-semibold text-[#0F0E17]">
          <Volume2 className="w-3.5 h-3.5 text-[#6344E7]" />
          <span>Call recording</span>
        </span>
        <span className="font-mono text-[11px] text-[#524E5E]">{formatDuration(call.durationSec)}</span>
      </div>

      <audio
        ref={audioRef}
        onTimeUpdate={onTimeUpdate}
        onEnded={() => setPlaying(false)}
        preload="none"
        className="hidden"
      />

      <div className="flex items-center gap-2">
        <TactileButton
          variant="secondary"
          size="sm"
          icon={playing ? Pause : Play}
          loading={loading}
          onClick={toggle}
          data-testid="call-recording-toggle"
        >
          {playing ? 'Pause' : 'Play'}
        </TactileButton>
        <div className="flex-1 h-1.5 rounded-full bg-[#E4E2EB] overflow-hidden">
          <div
            className="h-full bg-[#6344E7] transition-[width] duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>
        <a
          href={`${src}?download=true`}
          download
          aria-label="Download recording"
          className="p-2 rounded-lg border border-[#E4E2EB] bg-white text-[#524E5E] hover:text-[#0F0E17]"
        >
          <Download className="w-3.5 h-3.5" />
        </a>
      </div>

      <span className="text-[10px] text-[#524E5E]">
        {call.costInr != null
          ? `₹${Number(call.costInr).toFixed(2)}`
          : call.costUsd != null
            ? `$${Number(call.costUsd).toFixed(3)}`
            : 'Billed after the call'}
        {reasonLabel ? ` · ${reasonLabel}` : ''}
        {voiceLabel ? ` · ${voiceLabel}` : ''}
      </span>
    </div>
  );
}

export function CallsModule({ onRequireFunds = null }) {
  const {
    calls,
    selectedCallId,
    setSelectedCallId,
    agents,
    phoneNumbers,
    wallet,
    loadWorkspaceData,
  } = useWorkspace();
  const [filterDirection, setFilterDirection] = useState('All');
  const [filterAgentId, setFilterAgentId] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [agentId, setAgentId] = useState('');
  const [dialBusy, setDialBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [mainTab, setMainTab] = useState('history');
  const [historyBucket, setHistoryBucket] = useState('all');
  const [outcome, setOutcome] = useState(null);
  const [outcomeLoading, setOutcomeLoading] = useState(false);
  const [callbacks, setCallbacks] = useState([]);
  const [callbackBusy, setCallbackBusy] = useState(false);
  const [callbackTarget, setCallbackTarget] = useState('');

  useEffect(() => {
    const stored =
      typeof window !== 'undefined' ? sessionStorage.getItem('voxly_calls_agent') : null;
    if (stored && agents.some((a) => a.id === stored)) {
      setAgentId(stored);
      setFilterAgentId(stored);
      sessionStorage.removeItem('voxly_calls_agent');
    }
  }, [agents]);

  useEffect(() => {
    if (agents[0]?.id && !agentId) setAgentId(agents[0].id);
  }, [agents, agentId]);

  // The status tab is a server-side filter, so refetch rather than filter locally.
  // Keeping the full list in context means the other tabs stay instant.
  const [statusCalls, setStatusCalls] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const loadByStatus = useCallback(
    async (bucket) => {
      const status = bucketToApiStatus(bucket);
      if (!status) {
        setStatusCalls(null);
        return;
      }
      setStatusLoading(true);
      try {
        const rows = await api.calls.list({ statuses: [status], limit: 100 });
        setStatusCalls(rows);
      } catch (e) {
        showToast(e.message || 'Could not load calls', 'error');
        setStatusCalls(null);
      } finally {
        setStatusLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadByStatus(historyBucket);
  }, [historyBucket, loadByStatus]);

  const refreshCalls = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadWorkspaceData?.();
      await loadByStatus(historyBucket);
      showToast('Call list updated', 'success');
    } catch (e) {
      showToast(e.message || 'Could not refresh', 'error');
    } finally {
      setRefreshing(false);
    }
  }, [loadWorkspaceData, historyBucket, loadByStatus]);

  // Tab counts always describe the whole (unfiltered-by-status) list.
  const bucketCounts = useMemo(() => {
    const acc = { all: 0 };
    for (const status of CALL_STATUS_TABS) {
      if (status.id !== 'all') acc[status.id] = 0;
    }
    for (const c of calls) {
      acc.all += 1;
      const status = callStatus(c);
      if (acc[status] != null) acc[status] += 1;
    }
    return acc;
  }, [calls]);

  const scopedCalls = statusCalls ?? calls;

  const filteredCalls = useMemo(
    () =>
      scopedCalls.filter((call) => {
        const matchesAgent =
          filterAgentId === 'all' ||
          call.agentId === filterAgentId ||
          call.agentName === agents.find((a) => a.id === filterAgentId)?.name;
        const matchesDir =
          filterDirection === 'All' ||
          String(call.direction || '').toLowerCase() === filterDirection.toLowerCase();
        const q = searchQuery.trim().toLowerCase();
        const matchesSearch =
          !q ||
          (call.callerName || '').toLowerCase().includes(q) ||
          (call.callerPhone || '').includes(q) ||
          (call.agentName || '').toLowerCase().includes(q) ||
          (call.outcome || '').toLowerCase().includes(q) ||
          (call.summary || '').toLowerCase().includes(q);
        return matchesDir && matchesSearch && matchesAgent;
      }),
    [scopedCalls, filterAgentId, filterDirection, searchQuery, agents]
  );

  const activeCall = useMemo(
    () =>
      filteredCalls.find((c) => c.id === selectedCallId) ||
      (filteredCalls.length > 0 ? filteredCalls[0] : null),
    [filteredCalls, selectedCallId]
  );

  useEffect(() => {
    if (!activeCall?.id) {
      setTranscriptLines([]);
      return;
    }
    let cancelled = false;
    if (!activeCall.connected) {
      setTranscriptLines([]);
      return;
    }
    api.calls
      .transcript(activeCall.id)
      .then((data) => {
        if (!cancelled) setTranscriptLines(data.lines || []);
      })
      .catch(() => {
        if (!cancelled) setTranscriptLines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCall?.id, activeCall?.connected]);

  // Structured post-call outcome: disposition, AI summary, extracted fields.
  useEffect(() => {
    if (!activeCall?.id || !activeCall.connected) {
      setOutcome(null);
      return;
    }
    let cancelled = false;
    setOutcomeLoading(true);
    api.calls
      .outcome(activeCall.id)
      .then((data) => {
        if (!cancelled) setOutcome(data.outcome || null);
      })
      .catch(() => {
        if (!cancelled) setOutcome(null);
      })
      .finally(() => {
        if (!cancelled) setOutcomeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCall?.id, activeCall?.connected]);

  useEffect(() => {
    if (!activeCall?.id) {
      setCallbacks([]);
      return;
    }
    let cancelled = false;
    api.calls
      .listCallbacks(activeCall.id)
      .then((rows) => {
        if (!cancelled) setCallbacks(rows || []);
      })
      .catch(() => {
        if (!cancelled) setCallbacks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCall?.id]);

  useEffect(() => {
    setCallbackTarget('');
  }, [activeCall?.id]);

  const placeCall = async () => {
    if (!agentId || !toNumber.trim()) return;
    // Payment wall: an empty wallet cannot place a billable call.
    if (balanceUsd <= 0 && balanceInr <= 0) {
      onRequireFunds?.();
      return;
    }
    setDialBusy(true);
    try {
      await api.calls.triggerOutbound({
        agentId,
        toE164: toNumber.trim(),
        fromE164: fromNumber || null,
      });
      showToast('Outgoing call started', 'success');
      await refreshCalls();
    } catch (e) {
      if (e.status === 402 || e.code === 'insufficient_balance') {
        onRequireFunds?.();
      } else {
        showToast(e.message || 'Could not place call', 'error');
      }
    } finally {
      setDialBusy(false);
    }
  };

  /**
   * Call a missed caller back. Uses the server's callback endpoint, which reuses
   * the normal outbound path — so wallet, agent and concurrency checks all apply.
   */
  const callBack = async () => {
    if (!activeCall?.id) return;
    const target = callbackTarget.trim() || activeCall.callerPhone || '';
    if (!target) {
      showToast('Enter the number to call back', 'error');
      return;
    }
    setCallbackBusy(true);
    try {
      const result = await api.calls.callback(activeCall.id, {
        toE164: target,
        agentId: activeCall.agentId || agentId || undefined,
      });
      if (result?.ok) {
        showToast(`Calling back ${target}`, 'success');
      } else {
        showToast(result?.error || 'Could not place the callback', 'error');
      }
      await refreshCalls();
    } catch (e) {
      showToast(e.message || 'Could not place the callback', 'error');
    } finally {
      setCallbackBusy(false);
    }
  };

  const canCallBack = Boolean(activeCall) && isCallbackCandidate(activeCall);
  const summaryText = activeCall?.summary || outcome?.summary_en || null;
  const extracted = outcome?.extracted_fields || outcome?.facts || null;
  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const walletEmpty = balanceUsd <= 0 && balanceInr <= 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Calls ({bucketCounts.all})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5 max-w-2xl">
            {PHONE_STACK_LABEL}: transcripts, recordings, and wallet usage for real phone conversations.
          </p>
        </div>
        <TactileButton
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          loading={refreshing}
          onClick={refreshCalls}
        >
          Refresh
        </TactileButton>
      </div>

      <div className="flex items-center gap-1 p-1 rounded-2xl bg-white border border-[#E4E2EB] w-fit">
        {[
          { id: 'history', label: 'Call history' },
          { id: 'outbound', label: 'Place outgoing call' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setMainTab(t.id)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold ${
              mainTab === t.id ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E] hover:text-[#0F0E17]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {mainTab === 'outbound' && (
        <SolidCard className="p-4 space-y-3">
          <div>
            <div className="text-xs font-bold text-[#0F0E17]">Outgoing call</div>
            <p className="text-[11px] text-[#524E5E] mt-1">
              Needs wallet balance, a published agent script, and a phone line as caller ID. Rate limits
              apply.
            </p>
          </div>

          {/* Payment wall, shown before the user tries to dial. */}
          {walletEmpty && (
            <div
              data-testid="calls-payment-wall"
              className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-xl bg-[#FFFBEB] border border-[#FDE68A]"
            >
              <p className="text-xs text-[#78350F]">
                Your wallet is empty. Add credit to place calls and receive callbacks.
              </p>
              <TactileButton
                variant="brand"
                size="sm"
                icon={CreditCard}
                onClick={() => onRequireFunds?.()}
                data-testid="calls-payment-wall-add"
              >
                Add credit
              </TactileButton>
            </div>
          )}

          <div className="grid sm:grid-cols-4 gap-2">
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            <select
              value={fromNumber}
              onChange={(e) => setFromNumber(e.target.value)}
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
            >
              <option value="">Agent phone line</option>
              {phoneNumbers.map((n) => (
                <option key={n.id} value={n.number}>
                  {n.label ? `${n.label} · ${n.number}` : n.number}
                </option>
              ))}
            </select>
            <input
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              placeholder="+91…"
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
            />
            <TactileButton variant="primary" size="sm" loading={dialBusy} onClick={placeCall}>
              Call now
            </TactileButton>
          </div>
        </SolidCard>
      )}

      {mainTab === 'history' && (
        <>
          {/* Canonical status tabs, driven by the server's status vocabulary. */}
          <div className="flex flex-wrap items-center gap-1 p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
            {CALL_STATUS_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                data-testid={`calls-status-${tab.id}`}
                onClick={() => setHistoryBucket(tab.id)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold ${
                  historyBucket === tab.id
                    ? 'bg-white text-[#0F0E17] shadow-xs'
                    : 'text-[#524E5E]'
                }`}
              >
                {tab.label} ({bucketCounts[tab.id] ?? 0})
              </button>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
                {['All', 'Inbound', 'Outbound'].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setFilterDirection(tab)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                      filterDirection === tab
                        ? 'bg-white text-[#0F0E17] shadow-xs'
                        : 'text-[#524E5E] hover:text-[#0F0E17]'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5 text-xs">
                <Filter className="w-3.5 h-3.5 text-[#8C879A]" />
                <select
                  value={filterAgentId}
                  onChange={(e) => setFilterAgentId(e.target.value)}
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2 py-1 text-xs"
                >
                  <option value="all">All agents</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="relative min-w-[240px]">
              <Search className="w-3.5 h-3.5 text-[#524E5E] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by caller, agent, outcome..."
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl pl-8 pr-3 py-1.5 text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className={`${activeCall ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
              <SolidCard padding="p-0" className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                        <th className="py-3 px-4">Caller</th>
                        <th className="py-3 px-3">Agent</th>
                        <th className="py-3 px-3">Status</th>
                        <th className="py-3 px-3 font-mono">Duration</th>
                        <th className="py-3 px-3">Outcome</th>
                        <th className="py-3 px-4 text-right">Time</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E4E2EB]">
                      {statusLoading && (
                        <tr>
                          <td colSpan={6} className="py-6 px-4 text-center text-[#8C879A]">
                            Loading calls…
                          </td>
                        </tr>
                      )}
                      {!statusLoading && filteredCalls.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-6 px-4 text-center text-[#8C879A]">
                            No calls match this filter yet.
                          </td>
                        </tr>
                      )}
                      {!statusLoading &&
                        filteredCalls.map((call) => {
                          const isSelected = activeCall && activeCall.id === call.id;
                          return (
                            <tr
                              key={call.id}
                              data-testid={`call-row-${call.status}`}
                              onClick={() => setSelectedCallId(call.id)}
                              className={`cursor-pointer transition-colors ${
                                isSelected ? 'bg-[#6344E7]/10 font-medium' : 'hover:bg-[#FAF9FD]'
                              }`}
                            >
                              <td className="py-3.5 px-4">
                                <div className="font-semibold text-[#0F0E17]">{call.callerName}</div>
                                <div className="text-[10px] font-mono text-[#524E5E]">
                                  {call.callerPhone || '—'}
                                </div>
                              </td>
                              <td className="py-3.5 px-3 text-[#524E5E] font-medium">{call.agentName}</td>
                              <td className="py-3.5 px-3">
                                <StatusPill status={call.status} />
                              </td>
                              <td className="py-3.5 px-3 font-mono font-bold text-[#0F0E17]">
                                {call.duration}
                              </td>
                              <td className="py-3.5 px-3">
                                <span className="text-[11px] text-[#524E5E] truncate max-w-[150px] block">
                                  {call.outcome}
                                </span>
                              </td>
                              <td className="py-3.5 px-4 text-right text-[11px] text-[#8C879A]">
                                {call.startedAt ? new Date(call.startedAt).toLocaleString() : '—'}
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </SolidCard>
            </div>

            {activeCall && (
              <div className="lg:col-span-5 space-y-4">
                <SolidCard className="space-y-4">
                  <div className="flex items-start justify-between pb-3 border-b border-[#E4E2EB]">
                    <div>
                      {/* A short reference for support, not the raw database id. */}
                      <span className="text-[10px] font-mono text-[#8C879A] uppercase">
                        {callReference(activeCall.id) ? `Call ${callReference(activeCall.id)}` : ''}
                      </span>
                      <h3 className="text-sm font-bold text-[#0F0E17] mt-0.5">
                        {activeCall.callerName}
                        {activeCall.callerPhone ? ` (${activeCall.callerPhone})` : ''}
                      </h3>
                    </div>
                    <StatusPill status={activeCall.status} />
                  </div>

                  {/* Why this call ended up with this status, in plain language. */}
                  <p className="text-[11px] text-[#524E5E]">
                    {statusMeta(activeCall.status).hint}
                    {!activeCall.connected ? ' This call never connected.' : ''}
                    {activeCall.policyReason ? ` (${activeCall.policyReason.replace(/_/g, ' ')})` : ''}
                  </p>

                  <RecordingPlayer call={activeCall} />

                  {/* Callback: the server dials through the normal outbound path. */}
                  {canCallBack && (
                    <div
                      data-testid="call-callback-panel"
                      className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2.5"
                    >
                      <div className="text-xs font-bold text-[#0F0E17]">Call this person back</div>
                      <p className="text-[11px] text-[#524E5E]">
                        Places a new call with {activeCall.agentName}. Uses your wallet balance and
                        phone line, exactly like an outgoing call.
                      </p>
                      <div className="flex flex-col sm:flex-row gap-2">
                        <input
                          value={callbackTarget}
                          onChange={(e) => setCallbackTarget(e.target.value)}
                          placeholder={activeCall.callerPhone || '+91…'}
                          data-testid="call-callback-number"
                          className="flex-1 bg-white border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
                        />
                        <TactileButton
                          variant="brand"
                          size="sm"
                          icon={PhoneCall}
                          loading={callbackBusy}
                          data-testid="call-callback-submit"
                          onClick={callBack}
                        >
                          Call back
                        </TactileButton>
                      </div>
                      {callbacks.length > 0 && (
                        <div className="pt-2 border-t border-[#E4E2EB] space-y-1">
                          {callbacks.map((cb) => (
                            <div
                              key={cb.callbackId}
                              className="flex items-center justify-between text-[10px] font-mono text-[#524E5E]"
                            >
                              <span>
                                {cb.toE164} · {cb.status}
                              </span>
                              <span>{cb.createdAt ? new Date(cb.createdAt).toLocaleString() : ''}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17]">
                      <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
                      <span>AI summary</span>
                    </div>
                    <p className="text-xs text-[#524E5E] leading-relaxed">
                      {summaryText ||
                        (outcomeLoading
                          ? 'Generating…'
                          : activeCall.connected
                            ? 'No summary yet. It appears once the call finishes processing.'
                            : 'No conversation, so there is nothing to summarise.')}
                    </p>

                    {extracted && Object.keys(extracted).length > 0 && (
                      <div className="pt-2 border-t border-[#E4E2EB] grid grid-cols-2 gap-2 text-[11px] font-mono">
                        {Object.entries(extracted).map(([k, v]) => (
                          <div
                            key={k}
                            className="bg-white p-2 rounded-lg border border-[#E4E2EB] shadow-2xs"
                          >
                            <span className="text-[#8C879A] block text-[9px] uppercase tracking-wider">
                              {k}
                            </span>
                            <span className="text-[#0F0E17] truncate block font-semibold">
                              {String(v)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {outcome?.disposition && (
                      <div className="pt-2 border-t border-[#E4E2EB] flex flex-wrap gap-1.5">
                        <StatusBadge status={outcome.disposition} size="xs" />
                        {(outcome.status_tags || []).slice(0, 6).map((tag) => (
                          <span
                            key={tag}
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-[#0F0E17] mb-2.5 flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-[#524E5E]" />
                      <span>Transcript ({transcriptLines.length} turns)</span>
                    </h4>

                    <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                      {transcriptLines.length === 0 && (
                        <p className="text-xs text-[#8C879A]">
                          {activeCall.connected
                            ? 'Transcript appears after the call finalizes.'
                            : 'This call never connected, so there is no transcript.'}
                        </p>
                      )}
                      {transcriptLines.map((t, idx) => {
                        const isAgent =
                          (t.role || t.speaker) === 'assistant' || t.role === 'agent';
                        return (
                          <div
                            key={idx}
                            className={`p-3 rounded-xl text-xs leading-relaxed ${
                              isAgent
                                ? 'bg-white border border-[#E4E2EB] ml-3 shadow-2xs'
                                : 'bg-[#FAF9FD] border border-[#E4E2EB] mr-3'
                            }`}
                          >
                            <div className="flex items-center justify-between text-[10px] text-[#8C879A] mb-1 font-mono">
                              <span
                                className={`font-bold ${isAgent ? 'text-[#6344E7]' : 'text-[#0F0E17]'}`}
                              >
                                {isAgent ? activeCall.agentName : 'Caller'}
                              </span>
                            </div>
                            <p className="text-[#0F0E17]">{t.text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </SolidCard>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
