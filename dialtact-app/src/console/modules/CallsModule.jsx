import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Volume2,
  FileText,
  RefreshCw,
  PhoneCall,
  PhoneIncoming,
  PhoneOutgoing,
  Voicemail,
  Play,
  Pause,
  Download,
  X,
  AlertTriangle,
  ListChecks,
  PhoneMissed,
  PhoneOff,
  Clock,
  WifiOff,
  Ban,
  CornerUpLeft,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { IntegrationSelectionSummary, useCallIntegrationOptions } from '../ui/CallIntegrationPicker';
import { OutboundCallForm, useOutboundCall } from './outbound/OutboundCallForm';
import { Badge, StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { PageHeader } from '../ui/PageHeader';
import { Tabs } from '../ui/Tabs';
import { Toolbar, SearchInput } from '../ui/Toolbar';
import { Avatar } from '../ui/Avatar';
import { EmptyState } from '../ui/EmptyState';
import { CallsTableSkeleton, CallDetailSkeleton, WaveformSkeleton } from '../ui/Skeleton';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import { bucketToApiStatus } from '../../lib/phoneLabels';
import {
  CALL_STATUS_TABS,
  bucketOutcome,
  callStatus,
  formatDuration,
  isCallbackCandidate,
  outcomeMeta,
  statusMeta,
} from '../../lib/callStatus';
import {
  callReference,
  dispositionLabel,
  endReasonLabel,
  humanizeToken,
  isTechnicalFailure,
  pipelineLabel,
  policyReasonLabel,
  statusWord,
  tagLabel,
  tagTone,
} from '../../lib/internalLabels';
import { formatInr, formatUsd, relativeTime } from '../../lib/money';
import { contactName, maskPhone } from '../../lib/phoneMask';
import { normalizeCall } from '../../services/apiNormalize';
import { fetchCallRecord } from './home/activityDetail';

const STATUS_ICON = {
  answered: PhoneIncoming,
  missed: PhoneIncoming,
  voicemail: Voicemail,
  outbound: PhoneOutgoing,
  declined: PhoneOutgoing,
  failed: PhoneOutgoing,
  in_progress: PhoneCall,
};

/** callStatus tones → Badge tones (DESIGN.md: red only for failures). */
const STATUS_TONE = { success: 'success', warning: 'warning', danger: 'danger', info: 'info', muted: 'neutral' };

const FIELD =
  'h-11 sm:h-9 w-full min-w-0 rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';
const SELECT =
  'h-11 sm:h-9 min-w-0 max-w-full sm:max-w-[14rem] rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';

/** One icon per reason a call never connected, so busy, declined and phone-off read apart. */
const OUTCOME_ICON = {
  no_answer: PhoneMissed,
  missed_call: PhoneMissed,
  declined: PhoneOff,
  busy: Clock,
  unreachable: WifiOff,
  invalid_number: Ban,
  connect_failed: AlertTriangle,
  voicemail: Voicemail,
};

function CallStatusPill({ status, kind = null, label = null, title = null, className = '' }) {
  const meta = statusMeta(status);
  const outcome = outcomeMeta(kind);
  const Icon = (kind && OUTCOME_ICON[kind]) || STATUS_ICON[status] || PhoneIncoming;
  const tone = status === 'in_progress' ? 'live' : outcome?.tone || STATUS_TONE[meta.tone] || 'neutral';
  // `label` is the server's plain outcome ("No answer", "Busy", "Missed call").
  return (
    <Badge tone={tone} title={title || outcome?.next || meta.hint} className={className} data-testid="call-outcome-pill">
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label || outcome?.label || meta.short}
    </Badge>
  );
}

const CALLBACK_MODE_WORD = { manual: 'Callback', ai_redial: 'AI redial', scheduled: 'Scheduled callback' };

/** "Callback by Priya": this call returned an earlier one. */
function CallbackOfBadge({ callbackOf }) {
  if (!callbackOf) return null;
  const word = CALLBACK_MODE_WORD[callbackOf.mode] || 'Callback';
  return (
    <Badge tone="info" data-testid="call-callback-of" title="This call returned an earlier call">
      <CornerUpLeft className="h-3 w-3" aria-hidden="true" />
      {callbackOf.by ? `${word} by ${callbackOf.by}` : word}
    </Badge>
  );
}

/** "Called back 2× · Answered": what happened when this call was returned. */
function CalledBackBadge({ callbacks }) {
  if (!callbacks?.count) return null;
  const times = callbacks.count > 1 ? `Called back ${callbacks.count}×` : 'Called back';
  return (
    <Badge tone="neutral" data-testid="call-called-back" title="Calls placed to return this one">
      <CornerUpLeft className="h-3 w-3" aria-hidden="true" />
      {callbacks.last_result ? `${times} · ${callbacks.last_result}` : times}
    </Badge>
  );
}

/** The AI service failed mid-call: the outage message played and the line closed. */
function TechnicalIssuePill({ className = '' }) {
  return (
    <Badge
      tone="danger"
      title="The AI service failed during this call. The caller heard the outage message and the call was ended."
      data-testid="technical-issue-pill"
      className={className}
    >
      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
      Technical issue
    </Badge>
  );
}

/** Tags the owner must not miss (language switch, problems, follow-ups) come first. */
function tagPriority(tag) {
  const raw = String(tag || '').toLowerCase();
  if (raw === 'followup:language_switch') return 0;
  if (raw.startsWith('quality:') || raw.startsWith('action:')) return 1;
  if (raw.startsWith('followup:')) return 2;
  return 3;
}

function sortedTags(tags = []) {
  return [...tags].sort((a, b) => tagPriority(a) - tagPriority(b));
}

function CallTags({ tags = [], limit = 3 }) {
  if (!tags.length) return null;
  const shown = sortedTags(tags).slice(0, limit);
  const rest = tags.length - shown.length;
  return (
    <>
      {shown.map((tag) => (
        <Badge key={tag} tone={tagTone(tag)} size="xs" title={tagLabel(tag)}>
          {tagLabel(tag)}
        </Badge>
      ))}
      {rest > 0 && (
        <span className="text-meta text-fg-muted" title={sortedTags(tags).slice(limit).map(tagLabel).join(', ')}>
          +{rest} more
        </span>
      )}
    </>
  );
}

/** One plain sentence for what happened on a call, like the Home feed. */
function callSentence(call) {
  const who = contactName(call.callerName, call.callerPhone);
  const agent = call.agentName && call.agentName !== 'Unassigned' ? call.agentName : null;
  const outgoing = String(call.direction || '').toLowerCase() === 'outbound';
  switch (callStatus(call)) {
    case 'in_progress':
      return { actor: agent, text: `is on a call with ${who}` };
    case 'missed':
      return outgoing
        ? { actor: agent, text: `couldn't reach ${who}: no answer` }
        : { actor: null, text: `Missed call from ${who}` };
    case 'voicemail':
      return outgoing ? { actor: agent, text: `reached ${who}'s voicemail` } : { actor: null, text: `${who} reached voicemail` };
    case 'declined':
      return {
        actor: agent,
        text: `couldn't reach ${who}: ${call.outcomeLabel ? call.outcomeLabel.toLowerCase() : 'busy or declined'}`,
      };
    case 'failed':
      return { actor: agent, text: `couldn't connect to ${who}` };
    default:
      return outgoing ? { actor: agent, text: `called ${who}` } : { actor: agent, text: `answered ${who}` };
  }
}

function money(amount, currency) {
  return currency === 'INR' ? formatInr(Number(amount)) : formatUsd(Number(amount));
}

const TIER_LABEL = { low: 'Economy', medium: 'Standard', premium: 'Premium' };

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
      <div className="rounded-control border border-line bg-canvas p-3.5 space-y-1">
        <div className="flex items-center gap-1.5 text-ui font-semibold text-ink">
          <Volume2 className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
          <span>Recording</span>
        </div>
        <p className="text-meta text-fg-muted">
          {call?.connected
            ? 'The recording is being prepared. This updates on its own.'
            : 'The call never connected, so there is no recording.'}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-control border border-line bg-canvas p-3.5 space-y-2.5">
      <div className="flex items-center justify-between gap-2 text-ui">
        <span className="flex items-center gap-1.5 font-semibold text-ink">
          <Volume2 className="h-4 w-4 text-accent" aria-hidden="true" />
          <span>Recording</span>
        </span>
        <span className="font-mono tabular-nums text-meta text-fg-body">{formatDuration(call.durationSec)}</span>
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
          <div className="flex flex-1 items-center justify-center">
            <WaveformSkeleton />
          </div>
        ) : (
          <div className="h-1.5 flex-1 overflow-hidden rounded-pill bg-line">
            <div
              className="h-full bg-accent transition-[width] duration-200"
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
          title="Download recording"
          className="inline-flex h-11 w-11 sm:h-8 sm:w-8 items-center justify-center rounded-control border border-line bg-surface text-fg-body hover:border-line-strong hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
        >
          <Download className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {(reasonLabel || voiceLabel) && (
        <p className="text-meta text-fg-muted">
          {reasonLabel || ''}
          {reasonLabel && voiceLabel ? ' · ' : ''}
          {voiceLabel || ''}
        </p>
      )}
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
export function CallsModule({ onRequireFunds = null, agentId: lockedAgentId = null, agentName = '', embedded = false, initialSearch = '' }) {
  const {
    calls,
    selectedCallId,
    setSelectedCallId,
    agents,
    campaigns = [],
    phoneNumbers,
    wallet,
    loadWorkspaceData,
    refreshCalls: refreshWorkspaceCalls,
    isLoading,
  } = useWorkspace();
  const [filterDirection, setFilterDirection] = useState('All');
  const [filterAgentId, setFilterAgentId] = useState('all');
  const [tagFilter, setTagFilter] = useState('');
  const [availableTags, setAvailableTags] = useState([]);
  const [searchQuery, setSearchQuery] = useState(() => initialSearch || sessionStorage.getItem('dialtact_calls_search') || '');
  useEffect(() => { sessionStorage.removeItem('dialtact_calls_search'); }, []);
  // "Place a call" is a draft the tenant fills in and may leave mid-way: keep it for
  // this browser tab across page switches, and clear the number after a call.
  // Integrations belong to the agent they were picked for (null keeps the agent's
  // saved settings). The embedded history view never dials, so it keeps no draft.
  // The form itself is the shared outgoing-call form (OutboundCallForm), the same
  // one the agent workspace's test call and Outgoing tab use.
  const outboundCall = useOutboundCall({
    draftName: embedded ? null : 'place-call',
    draftSubject: 'all',
    extraDraft: { mainTab: 'history' },
    onRequireFunds: onRequireFunds ? () => onRequireFunds() : null,
    enabled: !embedded,
  });
  const dialDraft = outboundCall.draft;
  const patchDialDraft = outboundCall.patchDraft;
  const { agentId } = dialDraft;
  const setAgentId = useCallback((value) => patchDialDraft({ agentId: value }), [patchDialDraft]);
  const [refreshing, setRefreshing] = useState(false);
  const [transcriptLines, setTranscriptLines] = useState([]);
  const [liveTranscription, setLiveTranscription] = useState(null);
  const mainTab = dialDraft.mainTab === 'outbound' ? 'outbound' : 'history';
  const setMainTab = (value) => patchDialDraft({ mainTab: value });
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
      typeof window !== 'undefined' ? sessionStorage.getItem('dialtact_calls_agent') : null;
    if (stored && agents.some((a) => a.id === stored)) {
      setAgentId(stored);
      setFilterAgentId(stored);
      sessionStorage.removeItem('dialtact_calls_agent');
    }
  }, [agents, lockedAgentId]);

  useEffect(() => {
    if (lockedAgentId) return;
    // A remembered agent that no longer exists falls back to the first one.
    if (agents[0]?.id && (!agentId || !agents.some((a) => a.id === agentId))) setAgentId(agents[0].id);
  }, [agents, agentId, lockedAgentId, setAgentId]);

  // The status tab is a server-side filter, so refetch rather than filter locally.
  // Keeping the full list in context means the other tabs stay instant.
  const [statusCalls, setStatusCalls] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const statusRequest = React.useRef(0);
  const agentsById = useMemo(() => Object.fromEntries(agents.map(agent => [agent.id, agent])), [agents]);
  // Held in a ref so a changed agent list does not rebuild the loader and restart the poll.
  const agentsByIdRef = React.useRef(agentsById);
  agentsByIdRef.current = agentsById;

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
          agentMap: agentsByIdRef.current,
        });
        if (request === statusRequest.current) setStatusCalls(rows);
      } catch (e) {
        if (request === statusRequest.current && !quiet) showToast(e.message || 'Could not load calls', 'error');
      } finally {
        if (request === statusRequest.current) setStatusLoading(false);
      }
    },
    [lockedAgentId, tagFilter]
  );

  // Poll fast only while a call on screen is still in progress; otherwise slowly.
  const hasLiveCallRef = React.useRef(false);
  // The workspace already loaded the unfiltered tenant list; reuse it for the first paint.
  const workspaceCallsRef = React.useRef({ calls, isLoading });
  workspaceCallsRef.current = { calls, isLoading };
  useEffect(() => {
    let disposed = false;
    let timer;
    const schedule = () => {
      if (!disposed) timer = setTimeout(() => poll(true), hasLiveCallRef.current ? 5000 : 15000);
    };
    const poll = async (quiet = false) => {
      clearTimeout(timer);
      if (!quiet || document.visibilityState === 'visible') await loadByStatus(historyBucket, quiet);
      schedule();
    };
    const seeded = !bucketToApiStatus(historyBucket) && !tagFilter && !lockedAgentId
      && !workspaceCallsRef.current.isLoading && workspaceCallsRef.current.calls.length > 0;
    if (seeded) schedule();
    else poll();
    const onVisible = () => { if (document.visibilityState === 'visible') poll(true); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      disposed = true;
      statusRequest.current += 1;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [historyBucket, loadByStatus, tagFilter, lockedAgentId]);

  const refreshCalls = useCallback(async () => {
    setRefreshing(true);
    try {
      await (refreshWorkspaceCalls || loadWorkspaceData)?.();
      await loadByStatus(historyBucket);
      await loadAvailableTags();
      showToast('Call list updated', 'success');
    } catch (e) {
      showToast(e.message || 'Could not refresh', 'error');
    } finally {
      setRefreshing(false);
    }
  }, [refreshWorkspaceCalls, loadWorkspaceData, historyBucket, loadByStatus, loadAvailableTags]);

  // Tab counts always describe the whole (unfiltered-by-status) list.
  const bucketCalls = useMemo(
    () => (lockedAgentId ? calls.filter((c) => c.agentId === lockedAgentId) : calls),
    [calls, lockedAgentId]
  );

  const baseCalls = statusCalls ?? bucketCalls;
  // A call opened from a deep link (Home feed) may be older than the first page of
  // history: fetch that one row and show it at the top so it can be selected.
  const [linkedCall, setLinkedCall] = useState(null);
  const linkedRequest = React.useRef('');
  const selectedListed = Boolean(selectedCallId) && baseCalls.some((c) => c.id === selectedCallId);
  useEffect(() => {
    if (!selectedCallId || selectedListed || isLoading || statusLoading) return undefined;
    if (linkedCall?.id === selectedCallId || linkedRequest.current === selectedCallId) return undefined;
    linkedRequest.current = selectedCallId;
    let active = true;
    fetchCallRecord(selectedCallId)
      .then((row) => { if (active && row) setLinkedCall(normalizeCall(row, agentsByIdRef.current)); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [selectedCallId, selectedListed, isLoading, statusLoading, linkedCall]);
  const scopedCalls = useMemo(
    () => (linkedCall && !baseCalls.some((c) => c.id === linkedCall.id) && (!lockedAgentId || linkedCall.agentId === lockedAgentId)
      ? [linkedCall, ...baseCalls]
      : baseCalls),
    [linkedCall, baseCalls, lockedAgentId]
  );
  hasLiveCallRef.current = scopedCalls.some((call) => callStatus(call) === 'in_progress');

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
        const phoneQuery = q.replace(/\D/g, '');
        const matchesPhone = phoneQuery.length >= 3 && /^[+\d\s().-]+$/.test(q) &&
          [call.callerPhone, call.calledPhone].some((phone) => String(phone || '').replace(/\D/g, '').includes(phoneQuery));
        const matchesSearch =
          !q ||
          matchesPhone ||
          (call.callerName || '').toLowerCase().includes(q) ||
          (call.callerPhone || '').includes(q) ||
          (call.agentName || '').toLowerCase().includes(q) ||
          (call.outcome || '').toLowerCase().includes(q) ||
          (call.summary || '').toLowerCase().includes(q) ||
          (call.statusTags || []).some((tag) => tag.includes(q));
        // "Busy" inside "Busy / declined" and similar narrow to one reason.
        const narrowed = bucketOutcome(historyBucket);
        const matchesOutcome = !narrowed || call.outcomeKind === narrowed;
        return matchesDir && matchesSearch && matchesAgent && matchesOutcome;
      }),
    [scopedCalls, filterAgentId, filterDirection, searchQuery, agents, historyBucket]
  );

  const activeCall = useMemo(
    () =>
      filteredCalls.find((c) => c.id === selectedCallId) ||
      (filteredCalls.length > 0 ? filteredCalls[0] : null),
    [filteredCalls, selectedCallId]
  );
  const activeCampaign = activeCall?.campaignId ? campaigns.find((c) => c.id === activeCall.campaignId) : null;
  const activeCallSelection = activeCall?.integrationSelection || activeCampaign?.integrations || null;
  const detailIntegrationOptions = useCallIntegrationOptions(activeCallSelection?.length ? activeCall?.agentId : null);

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

  const detailCaller = activeCall ? contactName(activeCall.callerName, activeCall.callerPhone) : '';
  const detailSentence = activeCall ? callSentence(activeCall) : null;
  const detailOutcome = activeCall ? dispositionLabel(outcome?.disposition || activeCall.disposition) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={embedded ? `${agentName || 'Agent'} calls` : 'Calls'}
        description="Every call your AI employees made or took, with recordings, transcripts and what each call cost."
        actions={
          <TactileButton
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            loading={refreshing}
            onClick={refreshCalls}
          >
            Refresh
          </TactileButton>
        }
      />

      {!embedded && (
        <Tabs
          label="Calls view"
          value={mainTab}
          onChange={setMainTab}
          items={[
            { id: 'history', label: 'Call history' },
            { id: 'outbound', label: 'Place a call' },
          ]}
        />
      )}

      {!embedded && mainTab === 'outbound' && (
        <SolidCard className="space-y-4">
          <div>
            <h2 className="text-title text-ink">Place a call</h2>
            <p className="mt-0.5 text-ui text-fg-muted">
              Your agent calls the number now. You need money in your wallet, a published agent and a phone line to call
              from. Calls per minute are limited.
            </p>
          </div>

          <OutboundCallForm
            call={outboundCall}
            ids={{
              root: 'calls-place-call-form',
              paymentWall: 'calls-payment-wall',
              paymentWallAdd: 'calls-payment-wall-add',
              agent: 'calls-place-call-agent',
              from: 'calls-place-call-from',
              to: 'calls-place-call-to',
              submit: 'calls-place-call-submit',
              integrationSummary: 'outbound-integration-summary',
              error: 'calls-place-call-error',
            }}
            onPlaced={() => refreshCalls()}
          />
        </SolidCard>
      )}

      {(embedded || mainTab === 'history') && (
        <>
          {/* Canonical status filter, driven by the server's status vocabulary. */}
          <Toolbar>
            <select
              aria-label="Call status"
              data-testid="calls-status-filter"
              value={historyBucket}
              onChange={(event) => setHistoryBucket(event.target.value)}
              className={SELECT}
            >
              {CALL_STATUS_TABS.map((tab) => <option key={tab.id} value={tab.id}>{tab.label}</option>)}
            </select>
            <Tabs
              label="Direction"
              value={filterDirection}
              onChange={setFilterDirection}
              items={[
                { id: 'All', label: 'All' },
                { id: 'Inbound', label: 'Incoming' },
                { id: 'Outbound', label: 'Outgoing' },
              ]}
            />
            <select
              value={filterAgentId}
              onChange={(e) => setFilterAgentId(e.target.value)}
              disabled={Boolean(lockedAgentId)}
              aria-label="Filter by agent"
              className={SELECT}
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
              className={SELECT}
            >
              <option value="">All tags</option>
              {availableTags.map(({ tag, count }) => (
                <option key={tag} value={tag}>
                  {tagLabel(tag)} ({count})
                </option>
              ))}
            </select>
            <Toolbar.Spacer />
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              label="Search calls"
              placeholder="Search name, number, agent or outcome"
              className="w-full sm:w-72"
            />
          </Toolbar>

          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
            <div className={`min-w-0 ${activeCall ? 'lg:col-span-7' : 'lg:col-span-12'}`}>
              <SolidCard padding="p-0" className="overflow-hidden">
                {statusLoading || (isLoading && !calls.length) ? (
                  <CallsTableSkeleton rows={6} />
                ) : filteredCalls.length === 0 ? (
                  <EmptyState
                    compact
                    icon={PhoneCall}
                    title="No calls match these filters"
                    description="Try another status, agent or tag, or clear the search."
                  />
                ) : (
                  <ul className="divide-y divide-line" aria-label="Calls">
                    {filteredCalls.map((call) => {
                      const isSelected = activeCall && activeCall.id === call.id;
                      const status = callStatus(call);
                      const sentence = callSentence(call);
                      const outcomeText = dispositionLabel(call.disposition) || call.summary || call.outcomeReason || null;
                      const masked = maskPhone(call.callerPhone);
                      const named = contactName(call.callerName, null, '') !== '';
                      return (
                        <li key={call.id}>
                          <button
                            type="button"
                            data-testid={`call-row-${call.status}`}
                            aria-current={isSelected ? 'true' : undefined}
                            onClick={() => setSelectedCallId(call.id)}
                            className={`relative flex w-full gap-3 px-4 py-3.5 text-left transition-colors sm:px-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent before:absolute before:left-0 before:top-3 before:bottom-3 before:w-[3px] before:rounded-r-full ${
                              isSelected ? 'bg-accent-soft before:bg-accent' : 'hover:bg-canvas before:bg-transparent'
                            }`}
                          >
                            {sentence.actor ? (
                              <Avatar name={call.agentName} size="sm" live={status === 'in_progress'} title={call.agentName} />
                            ) : (
                              <Avatar icon={STATUS_ICON[status] || PhoneIncoming} tone={status === 'missed' ? 'warning' : 'neutral'} size="sm" />
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="text-copy text-ink break-words">
                                {sentence.actor && <span className="font-semibold">{sentence.actor} </span>}
                                <span className={sentence.actor ? 'text-fg-body' : ''}>{sentence.text}</span>
                              </p>
                              {outcomeText && (
                                <p className="mt-0.5 line-clamp-2 text-ui text-fg-muted break-words" title={outcomeText}>
                                  {outcomeText}
                                </p>
                              )}
                              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-meta text-fg-muted">
                                <time
                                  dateTime={call.startedAt || undefined}
                                  title={call.startedAt ? new Date(call.startedAt).toLocaleString('en-IN') : undefined}
                                >
                                  {call.startedAt ? relativeTime(call.startedAt) : 'Time unknown'}
                                </time>
                                {named && masked && <span>· {masked}</span>}
                                {call.duration && call.duration !== '—' && (
                                  <span className="font-mono tabular-nums">· {call.duration}</span>
                                )}
                                {!sentence.actor && call.agentName && call.agentName !== 'Unassigned' && <span>· {call.agentName}</span>}
                                <CallStatusPill status={call.status} kind={call.outcomeKind} label={call.outcomeLabel} title={call.outcomeReason} />
                                <CallbackOfBadge callbackOf={call.callbackOf} />
                                <CalledBackBadge callbacks={call.callbacks} />
                                {isTechnicalFailure(call.endReason) && <TechnicalIssuePill />}
                                <CallTags tags={call.statusTags} />
                              </div>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </SolidCard>
            </div>

            {activeCall && (
              <div ref={detailRef} className="min-w-0 space-y-4 lg:col-span-5">
                <SolidCard className="space-y-4">
                  <div className="flex items-start gap-3 border-b border-line pb-4">
                    <Avatar name={activeCall.agentName} live={callStatus(activeCall) === 'in_progress'} title={activeCall.agentName} />
                    <div className="min-w-0 flex-1">
                      <h3 className="text-title text-ink break-words">{detailCaller}</h3>
                      <p className="text-ui text-fg-muted">
                        {activeCall.callerPhone && (
                          <span className="font-mono tabular-nums text-fg-body">{maskPhone(activeCall.callerPhone)}</span>
                        )}
                        {activeCall.callerPhone && callReference(activeCall.id) ? ' · ' : ''}
                        {/* A short reference for support, not the raw database id. */}
                        {callReference(activeCall.id) && (
                          <span>
                            Call <span className="font-mono tabular-nums">{callReference(activeCall.id)}</span>
                          </span>
                        )}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedCallId(null)}
                      className="-mr-1 -mt-1 inline-flex h-11 w-11 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-control text-fg-muted hover:bg-surface-subtle hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      title="Close details"
                      aria-label="Close details"
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>

                  <div className="space-y-2">
                    <p className="text-copy text-ink">
                      {detailSentence.actor && <span className="font-semibold">{detailSentence.actor} </span>}
                      <span className={detailSentence.actor ? 'text-fg-body' : ''}>{detailSentence.text}</span>
                      {detailOutcome && <span className="text-fg-body"> · {detailOutcome}</span>}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 text-meta text-fg-muted">
                      <CallStatusPill status={activeCall.status} kind={activeCall.outcomeKind} label={activeCall.outcomeLabel} title={activeCall.outcomeReason} />
                      <CallbackOfBadge callbackOf={activeCall.callbackOf} />
                      {isTechnicalFailure(activeCall.endReason) && <TechnicalIssuePill />}
                      {activeCall.startedAt && (
                        <time dateTime={activeCall.startedAt} title={new Date(activeCall.startedAt).toLocaleString('en-IN')}>
                          {relativeTime(activeCall.startedAt)}
                        </time>
                      )}
                      {activeCall.duration && activeCall.duration !== '—' && (
                        <span className="font-mono tabular-nums">· {activeCall.duration}</span>
                      )}
                    </div>
                    {/* Why this call ended up with this status, in plain language. */}
                    <p className="text-ui text-fg-muted" data-testid="call-outcome-reason">
                      {activeCall.outcomeReason || statusMeta(activeCall.status).hint}
                      {!activeCall.connected ? ' This call never connected.' : ''}
                      {activeCall.policyReason && !activeCall.outcomeReason && activeCall.direction !== 'outbound'
                        ? ` (${policyReasonLabel(activeCall.policyReason)})`
                        : ''}
                    </p>
                    {outcomeMeta(activeCall.outcomeKind) && (
                      <p className="text-ui text-fg-body" data-testid="call-outcome-next">
                        {outcomeMeta(activeCall.outcomeKind).next}
                      </p>
                    )}
                    {activeCall.callbackOf?.id && (
                      <p className="text-ui text-fg-muted" data-testid="call-callback-of-link">
                        This call returned an earlier call
                        {activeCall.callbackOf.at ? ` (placed ${relativeTime(activeCall.callbackOf.at)})` : ''}.{' '}
                        <button
                          type="button"
                          onClick={() => setSelectedCallId(activeCall.callbackOf.id)}
                          className="font-medium text-accent underline-offset-2 hover:underline"
                        >
                          Open the original call
                        </button>
                      </p>
                    )}
                    {activeCall.callbacks?.count > 0 && (
                      <p className="text-ui text-fg-muted" data-testid="call-callbacks-summary">
                        {activeCall.callbacks.count > 1 ? `Called back ${activeCall.callbacks.count} times` : 'Called back once'}
                        {activeCall.callbacks.last_at ? `, last ${relativeTime(activeCall.callbacks.last_at)}` : ''}
                        {activeCall.callbacks.last_result ? `: ${activeCall.callbacks.last_result.toLowerCase()}` : ''}.
                        Each callback is its own row in this list.
                      </p>
                    )}
                  </div>

                  <RecordingPlayer call={activeCall} />

                  <div className="rounded-control border border-line bg-canvas p-3.5 space-y-1.5" data-testid="call-integrations">
                    <div className="text-ui font-semibold text-ink">Integrations used on this call</div>
                    <IntegrationSelectionSummary
                      selection={activeCallSelection}
                      options={detailIntegrationOptions.items}
                      inherited={Boolean(activeCampaign?.integrations?.length && !activeCall?.integrationSelection)}
                      emptyText={activeCall?.campaignId && !activeCampaign
                        ? 'Uses the campaign’s integration settings.'
                        : 'None chosen: the agent’s saved integration settings applied.'}
                    />
                  </div>

                  {(activeCall.connected || activeCall.tier) && (
                    <dl className="divide-y divide-line rounded-control border border-line bg-canvas text-ui">
                      {activeCall.connected && (
                        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                          <dt className="text-fg-body">Call cost</dt>
                          <dd className="text-right font-semibold text-ink">
                            {activeCall.billedAmount != null ? (
                              <span className="font-mono tabular-nums">{money(activeCall.billedAmount, activeCall.billedCurrency)}</span>
                            ) : activeCall.inProgress ? 'Worked out after the call' : 'Not available'}
                          </dd>
                        </div>
                      )}
                      {activeCall.tier && (
                        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                          <dt className="text-fg-body">Voice quality</dt>
                          <dd data-testid={`call-tier-${activeCall.tier}`} className="font-semibold text-ink">
                            {TIER_LABEL[activeCall.tier] || humanizeToken(activeCall.tier)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  )}

                  {/* Callback: the server dials through the normal outbound path. */}
                  {canCallBack && (
                    <div
                      data-testid="call-callback-panel"
                      className="rounded-control border border-warning-line bg-warning-soft p-3.5 space-y-2.5"
                    >
                      <div className="text-ui font-semibold text-ink">Call {detailCaller} back</div>
                      <p className="text-meta text-fg-body">
                        {activeCall.agentName} places a new call from your phone line. It is charged to your wallet like
                        any outgoing call.
                      </p>
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <input
                          value={callbackTarget}
                          onChange={(e) => setCallbackTarget(e.target.value)}
                          placeholder={activeCall.callerPhone || '+91…'}
                          aria-label="Number to call back"
                          inputMode="tel"
                          data-testid="call-callback-number"
                          className={`${FIELD} flex-1 font-mono tabular-nums`}
                        />
                        <TactileButton
                          variant="primary"
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
                        <ul className="space-y-1 border-t border-warning-line pt-2">
                          {callbacks.map((cb) => (
                            <li key={cb.callbackId} className="flex flex-wrap items-center justify-between gap-x-3 text-meta text-fg-body">
                              <span>
                                <span className="font-mono tabular-nums">{cb.toE164}</span> · {statusWord(cb.status).label}
                              </span>
                              <time
                                dateTime={cb.createdAt || undefined}
                                title={cb.createdAt ? new Date(cb.createdAt).toLocaleString('en-IN') : undefined}
                                className="text-fg-muted"
                              >
                                {cb.createdAt ? relativeTime(cb.createdAt) : ''}
                              </time>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  <div className="rounded-control border border-line bg-canvas p-3.5 space-y-2">
                    <div className="flex items-center gap-1.5 text-ui font-semibold text-ink">
                      <ListChecks className="h-4 w-4 text-accent" aria-hidden="true" />
                      <span>Summary</span>
                    </div>
                    <div className="text-ui leading-relaxed text-fg-body">
                      {summaryText ? (
                        summaryText
                      ) : outcomeLoading ? (
                        <div className="flex items-center gap-2 py-1">
                          <WaveformSkeleton />
                          <span className="text-meta text-fg-muted">Writing the summary…</span>
                        </div>
                      ) : activeCall.connected ? (
                        'No summary yet. It appears once the call finishes processing.'
                      ) : (
                        'No conversation, so there is nothing to summarise.'
                      )}
                    </div>

                    {extracted && Object.keys(extracted).length > 0 && (
                      <dl className="grid grid-cols-1 gap-2 border-t border-line pt-2 sm:grid-cols-2">
                        {Object.entries(extracted).map(([k, v]) => (
                          <div key={k} className="min-w-0 rounded-control border border-line bg-surface p-2">
                            <dt className="text-meta text-fg-muted">{humanizeToken(k)}</dt>
                            <dd className="truncate text-ui font-semibold text-ink" title={String(v)}>
                              {String(v)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}

                    {outcome?.disposition && (
                      <div className="flex flex-wrap gap-1.5 border-t border-line pt-2">
                        <StatusBadge status={outcome.disposition} size="xs" />
                        {sortedTags(outcome.status_tags || []).slice(0, 12).map((tag) => (
                          <Badge key={tag} tone={tagTone(tag)} size="xs" title={tagLabel(tag)}>
                            {tagLabel(tag)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h4 className="mb-2.5 flex items-center gap-1.5 text-ui font-semibold text-ink">
                      <FileText className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
                      <span>Transcript</span>
                      <span className="font-normal text-fg-muted">
                        · <span className="font-mono tabular-nums">{transcriptLines.length}</span> {transcriptLines.length === 1 ? 'turn' : 'turns'}
                      </span>
                    </h4>
                    {liveTranscription && (() => {
                      const hasSavedText = transcriptLines.length > 0 || Number(liveTranscription.segments || 0) > 0;
                      const partial = liveTranscription.status === 'partial' || (liveTranscription.status === 'failed' && hasSavedText);
                      const label = partial
                        ? 'Partial — saved transcript available'
                        : ({ connecting: 'Connecting…', streaming: 'Listening', complete: 'Complete', failed: 'Could not transcribe this call' })[liveTranscription.status] || 'Status unavailable';
                      return <p className={`mb-2 text-ui ${liveTranscription.status === 'failed' && !hasSavedText ? 'text-danger-fg' : 'text-fg-body'}`} role="status">Live transcription: {label}</p>;
                    })()}

                    <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
                      {activeCall.connected && transcriptLines.length === 0 && outcomeLoading ? (
                        <div className="space-y-2 py-1 animate-pulse motion-reduce:animate-none">
                          <div className="mr-6 space-y-1.5 rounded-control border border-line bg-canvas p-3">
                            <div className="h-2.5 w-16 rounded-pill bg-line" />
                            <div className="h-3 w-4/5 rounded-pill bg-line/80" />
                          </div>
                          <div className="ml-6 space-y-1.5 rounded-control border border-line bg-surface p-3">
                            <div className="h-2.5 w-16 rounded-pill bg-line" />
                            <div className="h-3 w-3/4 rounded-pill bg-line/80" />
                          </div>
                        </div>
                      ) : transcriptLines.length === 0 ? (
                        <p className="text-ui text-fg-muted">
                          {activeCall.connected
                            ? 'The transcript appears once the call is processed.'
                            : 'This call never connected, so there is no transcript.'}
                        </p>
                      ) : null}
                      {transcriptLines.map((t, idx) => {
                        const isAgent =
                          (t.role || t.speaker) === 'assistant' || t.role === 'agent';
                        return (
                          <div
                            key={idx}
                            className={`rounded-control p-3 text-ui leading-relaxed ${
                              isAgent ? 'ml-3 border border-line bg-surface' : 'mr-3 border border-line bg-canvas'
                            }`}
                          >
                            <div className={`mb-1 text-meta font-semibold ${isAgent ? 'text-accent-fg' : 'text-ink'}`}>
                              {isAgent ? activeCall.agentName : 'Caller'}
                            </div>
                            <p className="text-ink break-words">{t.text}</p>
                          </div>
                        );
                      })}
                      {liveTranscription?.partial_text && (
                        <div className="mr-3 rounded-control border border-line bg-canvas p-3 text-ui" aria-label="Caller speech in progress">
                          <p className="mb-1 text-meta text-fg-muted">Caller · speaking</p>
                          <p className="text-fg-body">{liveTranscription.partial_text}</p>
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
