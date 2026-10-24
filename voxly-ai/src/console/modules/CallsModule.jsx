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
  X,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { CallsTableSkeleton, CallDetailSkeleton, WaveformSkeleton } from '../ui/Skeleton';
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
  const [ready, setReady] = useState(Boolean(call?.hasRecording));
  const blobRef = React.useRef(null);
  const fetchRef = React.useRef(null);
  const activeIdRef = React.useRef(call?.id);
  activeIdRef.current = call?.id;
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
    activeIdRef.current = call?.id;
    setPlaying(false);
    setProgress(0);
    setReady(Boolean(call?.hasRecording));
    return () => {
      activeIdRef.current = null;
      if (blobRef.current) URL.revokeObjectURL(blobRef.current);
      blobRef.current = null;
      fetchRef.current = null;
    };
  }, [call?.id]);

  useEffect(() => {
    if (call?.hasRecording) setReady(true);
    if (!call?.id || !call.connected) return undefined;
    let cancelled = false;
    let timer;
    const started = Date.now();
    const check = async () => {
      try {
        const status = await api.request('GET', `/api/call/${encodeURIComponent(call.id)}/audio-status`);
        if (!cancelled && status.ready === true) setReady(true);
        if (status.source === 'vobiz') return;
      } catch { /* Local audio may still be ready while the carrier finalizes. */ }
      if (!cancelled && Date.now() - started < 120000) timer = setTimeout(check, 5000);
    };
    check();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [call?.id, call?.connected, call?.hasRecording]);

  const loadRecording = () => {
    if (blobRef.current) return Promise.resolve(blobRef.current);
    if (!fetchRef.current) {
      const id = call.id;
      const promise = api.calls.recording(id).then(({ blob }) => {
        if (activeIdRef.current !== id) throw new Error('Recording selection changed.');
        const url = URL.createObjectURL(blob);
        blobRef.current = url;
        return url;
      }).finally(() => { if (fetchRef.current === promise) fetchRef.current = null; });
      fetchRef.current = promise;
    }
    return fetchRef.current;
  };

  const toggle = async () => {
    const el = audioRef.current;
    const id = call?.id;
    if (!el) return;
    if (!src || !api.getToken()) {
      showToast('Recording is not available', 'error');
      return;
    }
    if (!el.src) {
      setLoading(true);
      try {
        const url = await loadRecording();
        if (activeIdRef.current !== id || audioRef.current !== el) return;
        el.src = url;
        await el.play();
        if (activeIdRef.current === id) setPlaying(true);
      } catch {
        if (activeIdRef.current === id) showToast('Recording is not available yet', 'error');
      } finally {
        if (activeIdRef.current === id) setLoading(false);
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

  if (!call || !ready) {
    return (
      <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-[#0F0E17]">
          <Volume2 className="w-3.5 h-3.5 text-[#8C879A]" />
          <span>Call recording</span>
        </div>
        <p className="text-[11px] text-[#8C879A]">
          {call?.connected
            ? 'Recording is being prepared. This section updates automatically.'
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
        onError={() => {
          setLoading(false);
          setPlaying(false);
        }}
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
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <WaveformSkeleton />
          </div>
        ) : (
          <div className="flex-1 h-1.5 rounded-full bg-[#E4E2EB] overflow-hidden">
            <div
              className="h-full bg-[#6344E7] transition-[width] duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
        <button
          type="button"
          disabled={loading}
          onClick={async () => {
            setLoading(true);
            try {
              const res = await api.requestBinary('GET', `/api/call/${encodeURIComponent(call.id)}/audio/mix?download=1`, null,
                { Accept: 'audio/mpeg, audio/mp3' }, { allowMp3: true });
              const url = URL.createObjectURL(res.blob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `${call.id}-recording.mp3`;
              link.click();
              setTimeout(() => URL.revokeObjectURL(url), 10000);
            } catch (error) { showToast(error.message || 'Could not download recording', 'error'); }
            finally { setLoading(false); }
          }}
          aria-label="Download recording"
          className="p-2 rounded-lg border border-[#E4E2EB] bg-white text-[#524E5E] hover:text-[#0F0E17]"
        >
          <Download className="w-3.5 h-3.5" />
        </button>
      </div>

      <span className="text-[10px] text-[#524E5E]">
        {reasonLabel ? `${reasonLabel}` : ''}
        {voiceLabel ? ` · ${voiceLabel}` : ''}
      </span>
    </div>
  );
}

/**
 * Call history for the whole fleet, or for one agent.
 *
 * `agentId` locks every read and filter to that agent — the agent workspace's Calls
 * tab passes it, and nothing else changes: same endpoints, same payload, same
 * callback/transcript/outcome handling. `embedded` drops the page chrome (fleet
 * header, dialer tab) because the workspace supplies its own around it.
 */
export function CallsModule({ onRequireFunds = null, agentId: lockedAgentId = null, agentName = '', embedded = false }) {
  const {
    calls,
    selectedCallId,
    setSelectedCallId,
    agents,
    phoneNumbers,
    wallet,
    loadWorkspaceData,
    isLoading,
  } = useWorkspace();
  const [filterDirection, setFilterDirection] = useState('All');
  const [filterAgentId, setFilterAgentId] = useState('all');
  const [tagFilter, setTagFilter] = useState('');
  const [availableTags, setAvailableTags] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState('');
  const [agentId, setAgentId] = useState('');
  const [dialBusy, setDialBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [liveTranscription, setLiveTranscription] = useState(null);
  const [mainTab, setMainTab] = useState('history');
  const [historyBucket, setHistoryBucket] = useState('all');
  const [outcome, setOutcome] = useState(null);
  const [outcomeLoading, setOutcomeLoading] = useState(false);
  const [callbacks, setCallbacks] = useState([]);
  const [callbackBusy, setCallbackBusy] = useState(false);
  const [callbackTarget, setCallbackTarget] = useState('');
  const detailRef = React.useRef(null);

  useEffect(() => {
    if (selectedCallId && detailRef.current && typeof window !== 'undefined' && window.innerWidth < 1024) {
      detailRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedCallId]);

  useEffect(() => {
    if (lockedAgentId) {
      setAgentId(lockedAgentId);
      setFilterAgentId(lockedAgentId);
      return;
    }
    const stored =
      typeof window !== 'undefined' ? sessionStorage.getItem('voxly_calls_agent') : null;
    if (stored && agents.some((a) => a.id === stored)) {
      setAgentId(stored);
      setFilterAgentId(stored);
      sessionStorage.removeItem('voxly_calls_agent');
    }
  }, [agents, lockedAgentId]);

  useEffect(() => {
    if (lockedAgentId) return;
    if (agents[0]?.id && !agentId) setAgentId(agents[0].id);
  }, [agents, agentId, lockedAgentId]);

  // The status tab is a server-side filter, so refetch rather than filter locally.
  // Keeping the full list in context means the other tabs stay instant.
  const [statusCalls, setStatusCalls] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const statusRequest = React.useRef(0);
  const agentsById = useMemo(() => Object.fromEntries(agents.map(agent => [agent.id, agent])), [agents]);

  const loadAvailableTags = useCallback(async () => {
    try {
      setAvailableTags(await api.calls.tags({ agentId: lockedAgentId || undefined }));
    } catch {
      /* The menu keeps its current options during a transient outage. */
    }
  }, [lockedAgentId]);

  useEffect(() => {
    loadAvailableTags();
  }, [loadAvailableTags]);

  const loadByStatus = useCallback(
    async (bucket, quiet = false) => {
      const request = ++statusRequest.current;
      const status = bucketToApiStatus(bucket);
      if (!quiet) setStatusLoading(true);
      try {
        const rows = await api.calls.list({
          statuses: status ? [status] : undefined,
          agentId: lockedAgentId,
          tags: tagFilter ? [tagFilter] : undefined,
          limit: 100,
          agentMap: agentsById,
        });
        if (request === statusRequest.current) setStatusCalls(rows);
      } catch (e) {
        if (request === statusRequest.current && !quiet) showToast(e.message || 'Could not load calls', 'error');
      } finally {
        if (request === statusRequest.current) setStatusLoading(false);
      }
    },
    [lockedAgentId, agentsById, tagFilter]
  );

  useEffect(() => {
    let disposed = false;
    let timer;
    const poll = async (quiet = false) => {
      if (!quiet || document.visibilityState === 'visible') await loadByStatus(historyBucket, quiet);
      if (!disposed) timer = setTimeout(() => poll(true), 5000);
    };
    poll();
    return () => { disposed = true; statusRequest.current += 1; clearTimeout(timer); };
  }, [historyBucket, loadByStatus]);

  const refreshCalls = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadWorkspaceData?.();
      await loadByStatus(historyBucket);
      await loadAvailableTags();
      showToast('Call list updated', 'success');
    } catch (e) {
      showToast(e.message || 'Could not refresh', 'error');
    } finally {
      setRefreshing(false);
    }
  }, [loadWorkspaceData, historyBucket, loadByStatus, loadAvailableTags]);

  // Tab counts always describe the whole (unfiltered-by-status) list.
  const bucketCalls = useMemo(
    () => (lockedAgentId ? calls.filter((c) => c.agentId === lockedAgentId) : calls),
    [calls, lockedAgentId]
  );

  const scopedCalls = statusCalls ?? bucketCalls;

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
          (call.summary || '').toLowerCase().includes(q) ||
          (call.statusTags || []).some((tag) => tag.includes(q));
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
      setLiveTranscription(null);
      return;
    }
    let cancelled = false;
    if (!activeCall.connected) {
      setTranscriptLines([]);
      setLiveTranscription(null);
      return;
    }
    setTranscriptLines([]);
    setLiveTranscription(null);
    let timer;
    const poll = async () => {
      try {
        const data = await api.calls.transcript(activeCall.id);
        if (!cancelled) {
          setTranscriptLines(data.lines || []);
          setLiveTranscription(data.transcription || null);
        }
      } catch { /* Preserve already loaded lines during a transient outage. */ }
      if (!cancelled && callStatus(activeCall) === 'in_progress') timer = setTimeout(poll, 3000);
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [activeCall?.id, activeCall?.connected, activeCall?.status, activeCall?.endReason]);

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
            {embedded ? `${agentName || 'Agent'} calls` : 'Calls'}
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

      {!embedded && (
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
      )}

      {!embedded && mainTab === 'outbound' && (
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

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
            <select
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-base sm:text-xs min-h-[40px] sm:min-h-[34px]"
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
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-base sm:text-xs min-h-[40px] sm:min-h-[34px] font-mono"
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
              placeholder="+1…"
              className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-base sm:text-xs min-h-[40px] sm:min-h-[34px] font-mono"
            />
            <TactileButton variant="primary" size="sm" loading={dialBusy} onClick={placeCall} className="min-h-[40px] sm:min-h-[34px]">
              Call now
            </TactileButton>
          </div>
        </SolidCard>
      )}

      {(embedded || mainTab === 'history') && (
        <>
          {/* Canonical status tabs, driven by the server's status vocabulary. */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="Call status"
                data-testid="calls-status-filter"
                value={historyBucket}
                onChange={(event) => setHistoryBucket(event.target.value)}
                className="rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 text-sm min-h-[44px]"
              >
                {CALL_STATUS_TABS.map((tab) => <option key={tab.id} value={tab.id}>{tab.label}</option>)}
              </select>
              <div className="flex items-center p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
                {['All', 'Inbound', 'Outbound'].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setFilterDirection(tab)}
                    className={`px-3 py-1.5 min-h-[34px] rounded-lg text-xs font-semibold transition-all ${
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
                  disabled={Boolean(lockedAgentId)}
                  aria-label="Filter by agent"
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2 py-1.5 min-h-[36px] sm:min-h-[30px] text-base sm:text-xs disabled:opacity-50"
                >
                  <option value="all">All agents</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
                <select
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                  aria-label="Filter by tag"
                  data-testid="calls-tag-filter"
                  className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2 py-1.5 min-h-[36px] sm:min-h-[30px] text-base sm:text-xs"
                >
                  <option value="">All tags</option>
                  {availableTags.map(({ tag, count }) => (
                    <option key={tag} value={tag}>
                      {tag} ({count})
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
                      {statusLoading || (isLoading && !calls.length) ? (
                        <tr>
                          <td colSpan={6} className="p-0">
                            <CallsTableSkeleton rows={6} />
                          </td>
                        </tr>
                      ) : filteredCalls.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-6 px-4 text-center text-[#8C879A]">
                            No calls match this filter yet.
                          </td>
                        </tr>
                      ) : (
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
                                {call.statusTags?.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1 max-w-[170px]">
                                    {call.statusTags.slice(0, 3).map((tag) => (
                                      <span
                                        key={tag}
                                        title={tag}
                                        className="text-[9px] font-mono px-1 py-0.5 rounded bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]"
                                      >
                                        {tag.replace(/^[a-z]+:/, '')}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </td>
                              <td className="py-3.5 px-4 text-right text-[11px] text-[#8C879A]">
                                {call.startedAt ? new Date(call.startedAt).toLocaleString() : '—'}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </SolidCard>
            </div>

            {activeCall && (
              <div ref={detailRef} className="lg:col-span-5 space-y-4">
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
                    <div className="flex items-center gap-2">
                      <StatusPill status={activeCall.status} />
                      <button
                        type="button"
                        onClick={() => setSelectedCallId(null)}
                        className="p-1 rounded-lg text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] transition-colors"
                        title="Close details"
                        aria-label="Close details"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Why this call ended up with this status, in plain language. */}
                  <p className="text-[11px] text-[#524E5E]">
                    {statusMeta(activeCall.status).hint}
                    {!activeCall.connected ? ' This call never connected.' : ''}
                    {activeCall.policyReason ? ` (${activeCall.policyReason.replace(/_/g, ' ')})` : ''}
                  </p>

                  <RecordingPlayer call={activeCall} />

                  {activeCall.connected && (
                    <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between text-xs">
                      <span className="font-semibold text-[#524E5E]">Call cost</span>
                      <span className="font-mono font-bold text-[#0F0E17]">
                        {activeCall.billedAmount != null
                          ? `${activeCall.billedCurrency === 'INR' ? '₹' : '$'}${Number(activeCall.billedAmount).toFixed(2)}`
                          : activeCall.inProgress ? 'Finalized after the call' : 'Charge not available'}
                      </span>
                    </div>
                  )}

                  {activeCall.tier && (
                    <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between text-xs">
                      <span className="font-semibold text-[#524E5E]">Voice Stack Tier</span>
                      <span
                        data-testid={`call-tier-${activeCall.tier}`}
                        className="font-semibold text-[#6344E7] capitalize"
                      >
                        {{ low: 'Economical Tier', medium: 'Standard Regional Tier', premium: 'Flagship Live Tier' }[activeCall.tier] || activeCall.tier}
                      </span>
                    </div>
                  )}

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
                    <div className="text-xs text-[#524E5E] leading-relaxed">
                      {summaryText ? (
                        summaryText
                      ) : outcomeLoading ? (
                        <div className="flex items-center gap-2 py-1">
                          <WaveformSkeleton />
                          <span className="text-[11px] font-mono text-[#6344E7] animate-pulse">
                            Analyzing audio transcript &amp; outcomes…
                          </span>
                        </div>
                      ) : activeCall.connected ? (
                        'No summary yet. It appears once the call finishes processing.'
                      ) : (
                        'No conversation, so there is nothing to summarise.'
                      )}
                    </div>

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
                        {(outcome.status_tags || []).slice(0, 12).map((tag) => (
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
                    {liveTranscription && (() => {
                      const hasSavedText = transcriptLines.length > 0 || Number(liveTranscription.segments || 0) > 0;
                      const partial = liveTranscription.status === 'partial' || (liveTranscription.status === 'failed' && hasSavedText);
                      const label = partial
                        ? 'Partial — saved transcript available'
                        : ({ connecting: 'Connecting…', streaming: 'Listening', complete: 'Complete', failed: 'Could not transcribe this call' })[liveTranscription.status] || 'Status unavailable';
                      return <p className={`mb-2 text-xs ${liveTranscription.status === 'failed' && !hasSavedText ? 'text-[#B91C1C]' : 'text-[#524E5E]'}`} role="status">Live transcription: {label}</p>;
                    })()}

                    <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                      {/* chisel: conversational turn bubble skeletons while transcript is resolving */}
                      {activeCall.connected && transcriptLines.length === 0 && outcomeLoading ? (
                        <div className="space-y-2 animate-pulse py-1">
                          <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] mr-6 space-y-1.5">
                            <div className="h-2.5 w-16 bg-[#E4E2EB] rounded" />
                            <div className="h-3 w-4/5 bg-[#E4E2EB]/80 rounded" />
                          </div>
                          <div className="p-3 rounded-xl bg-white border border-[#E4E2EB] ml-6 space-y-1.5">
                            <div className="h-2.5 w-16 bg-[#E4E2EB] rounded" />
                            <div className="h-3 w-3/4 bg-[#E4E2EB]/80 rounded" />
                          </div>
                        </div>
                      ) : transcriptLines.length === 0 ? (
                        <p className="text-xs text-[#8C879A]">
                          {activeCall.connected
                            ? 'Transcript appears after the call finalizes.'
                            : 'This call never connected, so there is no transcript.'}
                        </p>
                      ) : null}
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
                      {liveTranscription?.partial_text && (
                        <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] mr-3 text-sm" aria-label="Caller speech in progress">
                          <p className="mb-1 text-[10px] text-[#8C879A]">Caller · speaking</p>
                          <p className="text-[#524E5E]">{liveTranscription.partial_text}</p>
                        </div>
                      )}
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
