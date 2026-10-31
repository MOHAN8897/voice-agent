import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Headphones,
  Megaphone,
  MessageSquareText,
  PhoneCall,
  UserRound,
  X,
} from 'lucide-react';
import { Badge, StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { Skeleton } from '../../ui/Skeleton';
import { api } from '../../../services/api';
import { formatClock, formatInr, formatUsd, relativeTime } from '../../../lib/money';
import { formatPhone, looksLikePhone } from '../../../lib/phoneMask';
import { callReference, endReasonLabel, statusWord, tagLabel, tagTone } from '../../../lib/internalLabels';
import { ItemAvatar, ItemSentence, PRIMARY_KINDS, iconFor } from './FeedItem';
import { fetchItemDetail, itemTargets } from './activityDetail';
import { drawerSpring, EASE_OUT } from './motion';

const FOCUSABLE = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], audio[controls], summary, [tabindex="0"]';

function fullDate(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function useIsPhone() {
  const query = '(max-width: 639px)';
  const [phone, setPhone] = useState(() => typeof window !== 'undefined' && window.matchMedia?.(query).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return undefined;
    const update = () => setPhone(mq.matches);
    mq.addEventListener?.('change', update);
    return () => mq.removeEventListener?.('change', update);
  }, []);
  return phone;
}

/** Loads the item's detail; keeps the last good result while a new id loads. */
function useItemDetail(itemId, refreshKey) {
  const [state, setState] = useState({ id: null, data: null, error: '', loading: false });
  useEffect(() => {
    if (!itemId) return undefined;
    let active = true;
    setState((s) => ({ id: itemId, data: s.id === itemId ? s.data : null, error: '', loading: true }));
    fetchItemDetail(itemId)
      .then((data) => active && setState({ id: itemId, data, error: '', loading: false }))
      .catch((e) => active && setState({
        id: itemId,
        data: null,
        error: e?.status === 404 || /not found|no longer/i.test(e?.message || '') ? 'This activity is no longer available.' : (e?.message || 'Could not load the details.'),
        loading: false,
      }));
    return () => { active = false; };
  }, [itemId, refreshKey]);
  return state.id === itemId ? state : { id: itemId, data: null, error: '', loading: true };
}

function Field({ label, children, mono = false }) {
  if (children == null || children === '' || children === false) return null;
  return (
    <div className="min-w-0">
      <dt className="text-meta text-fg-muted">{label}</dt>
      <dd className={`mt-0.5 break-words text-ui text-ink ${mono ? 'font-mono tabular-nums' : ''}`}>{children}</dd>
    </div>
  );
}

function Block({ title, icon: Icon, children, action = null }) {
  return (
    <section className="space-y-3 border-t border-line px-5 py-4 sm:px-6">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-ui font-semibold text-ink">
          {Icon && <Icon className="h-4 w-4 text-fg-subtle" aria-hidden="true" />}
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function RelatedList({ items, agentNames, now, onOpenItem }) {
  if (!items?.length) return null;
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-control border border-line">
      {items.map((rel) => {
        const Icon = iconFor(rel.type);
        return (
          <li key={rel.id}>
            <button
              type="button"
              onClick={() => onOpenItem(rel)}
              className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-fg-subtle" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <ItemSentence item={rel} className="block text-ui" />
                <span className="mt-0.5 block text-meta text-fg-muted">
                  {relativeTime(rel.at, now)}
                  {!rel.actor && agentNames[rel.agentId] ? ` · ${agentNames[rel.agentId]}` : ''}
                </span>
              </span>
              {rel.needsAction && <Badge tone="warning" size="xs">Needs you</Badge>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Transcript({ callId, agentName, live }) {
  const [state, setState] = useState({ lines: [], loading: true, error: '' });
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true;
    let timer;
    setState({ lines: [], loading: true, error: '' });
    const load = async () => {
      try {
        const data = await api.calls.transcript(callId);
        if (active) setState({ lines: data?.lines || [], loading: false, error: '' });
      } catch (e) {
        if (active) setState((s) => ({ ...s, loading: false, error: s.lines.length ? '' : (e?.message || 'The transcript is not available.') }));
      }
      if (active && live) timer = setTimeout(load, 3000);
    };
    load();
    return () => { active = false; clearTimeout(timer); };
  }, [callId, live]);

  if (state.loading) {
    return (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-12 w-4/5" />
        <Skeleton className="ml-auto h-12 w-3/4" />
      </div>
    );
  }
  if (state.error) return <p className="text-ui text-fg-muted">{state.error}</p>;
  if (!state.lines.length) return <p className="text-ui text-fg-muted">{live ? 'Waiting for the first words…' : 'No transcript was saved for this call.'}</p>;
  const lines = open ? state.lines : state.lines.slice(0, 6);
  return (
    <div className="space-y-2">
      <ol className="space-y-2" aria-label="Transcript">
        {lines.map((t, idx) => {
          const isAgent = (t.role || t.speaker) === 'assistant' || t.role === 'agent';
          return (
            <li key={idx} className={`rounded-control border border-line p-3 text-ui ${isAgent ? 'ml-4 bg-surface' : 'mr-4 bg-canvas'}`}>
              <div className={`mb-0.5 text-meta font-semibold ${isAgent ? 'text-accent-fg' : 'text-ink'}`}>{isAgent ? agentName || 'Agent' : 'Caller'}</div>
              <p className="break-words text-fg-body">{t.text}</p>
            </li>
          );
        })}
      </ol>
      {state.lines.length > 6 && (
        <TactileButton variant="ghost" size="xs" icon={open ? ChevronUp : ChevronDown} onClick={() => setOpen((v) => !v)}>
          {open ? 'Show less' : `Show all ${state.lines.length} turns`}
        </TactileButton>
      )}
    </div>
  );
}

function Recording({ callId }) {
  const [state, setState] = useState({ url: '', loading: false, error: '' });
  useEffect(() => () => { if (state.url) URL.revokeObjectURL(state.url); }, [state.url]);
  useEffect(() => { setState({ url: '', loading: false, error: '' }); }, [callId]);
  const load = async () => {
    setState({ url: '', loading: true, error: '' });
    try {
      const res = await api.calls.recording(callId);
      setState({ url: URL.createObjectURL(res?.blob || res), loading: false, error: '' });
    } catch (e) {
      setState({ url: '', loading: false, error: e?.message || 'The recording is not available.' });
    }
  };
  if (state.url) return <audio controls autoPlay src={state.url} className="w-full" aria-label="Call recording" />;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <TactileButton variant="secondary" size="sm" icon={Headphones} loading={state.loading} onClick={load}>
        Load recording
      </TactileButton>
      {state.error && <p role="alert" className="text-ui text-danger-fg">{state.error}</p>}
    </div>
  );
}

function money(charge) {
  if (!charge || charge.amount == null) return null;
  return String(charge.currency || '').toUpperCase() === 'USD' ? formatUsd(charge.amount) : formatInr(charge.amount);
}

function CallBlock({ call, item, now, title }) {
  const outbound = call.direction === 'outbound';
  const phone = outbound ? call.called_phone : call.caller_phone;
  const contactName = item.contact?.name || (call.customer && !looksLikePhone(call.customer) ? call.customer : null);
  const phoneLabel = formatPhone(phone) || item.contact?.phone || null;
  const live = call.in_progress || call.status === 'in_progress';
  const elapsed = live && call.started_at ? (now - new Date(call.started_at).getTime()) / 1000 : null;
  const duration = elapsed != null ? formatClock(elapsed) : call.duration_sec ? formatClock(call.duration_sec) : null;
  const tags = (call.status_tags || []).map((t) => ({ tag: t, label: tagLabel(t), tone: tagTone(t) })).filter((t) => t.label);
  return (
    <Block title={title} icon={PhoneCall} action={callReference(call.call_id) ? <span className="font-mono text-meta tabular-nums text-fg-muted">{callReference(call.call_id)}</span> : null}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Agent">{call.agent_name || 'Agent'}</Field>
        <Field label="Contact">
          {contactName ? (
            <>
              {contactName}
              {phoneLabel && <span className="block font-mono text-meta tabular-nums text-fg-body">{phoneLabel}</span>}
            </>
          ) : (
            phoneLabel ? <span className="font-mono tabular-nums">{phoneLabel}</span> : 'Unknown caller'
          )}
        </Field>
        <Field label="Direction">{outbound ? 'Outgoing' : 'Incoming'}</Field>
        <Field label="Status"><StatusBadge status={call.status} size="xs" /></Field>
        <Field label="Started"><span title={fullDate(call.started_at) || undefined}>{fullDate(call.started_at)}</span></Field>
        <Field label={live ? 'On the call for' : 'Duration'} mono>{duration}</Field>
        <Field label="Outcome">{call.outcome_label}</Field>
        <Field label="Cost" mono>{money(call.tenant_charge)}</Field>
        <Field label="How it ended">{endReasonLabel(call.end_reason)}</Field>
      </dl>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Tags">
          {tags.map((t) => <Badge key={t.tag} tone={t.tone} size="xs">{t.label}</Badge>)}
        </div>
      )}
      {call.summary && (
        <div className="rounded-control bg-canvas p-3">
          <p className="text-meta font-medium text-fg-muted">Summary</p>
          <p className="mt-1 text-ui text-fg-body break-words">{call.summary}</p>
        </div>
      )}
    </Block>
  );
}

function CampaignBlock({ campaign }) {
  const { total = 0, done = 0 } = campaign.progress || {};
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <Block title="Campaign" icon={Megaphone}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-copy font-semibold text-ink">{campaign.name}</span>
        <StatusBadge status={campaign.status} size="xs" />
      </div>
      {campaign.description && <p className="text-ui text-fg-body">{campaign.description}</p>}
      <div>
        <div className="flex justify-between text-meta text-fg-muted">
          <span>Progress</span>
          <span className="font-mono tabular-nums">{done} of {total} · {pct}%</span>
        </div>
        <div className="mt-1.5 h-2 overflow-hidden rounded-pill bg-surface-subtle" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Campaign progress">
          <motion.div className="h-full rounded-pill bg-accent" initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.3, ease: EASE_OUT }} />
        </div>
      </div>
      {Object.keys(campaign.statusCounts || {}).length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          {Object.entries(campaign.statusCounts).map(([status, count]) => (
            <Field key={status} label={statusWord(status).label} mono>{count.toLocaleString('en-IN')}</Field>
          ))}
        </dl>
      )}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Created">{fullDate(campaign.createdAt)}</Field>
        <Field label="Calls at once" mono>{campaign.concurrency}</Field>
        <Field label="Run started">{fullDate(campaign.run?.startedAt)}</Field>
        <Field label="Run ended">{fullDate(campaign.run?.endedAt)}</Field>
      </dl>
    </Block>
  );
}

function LeadBlock({ lead }) {
  const a = lead.assessment;
  return (
    <Block title="Lead" icon={UserRound}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Name">{lead.name}</Field>
        <Field label="Stage"><StatusBadge status={lead.stage} size="xs" /></Field>
        <Field label="Score">
          {a && a.score != null ? (
            <span className="inline-flex items-center gap-2">
              <span className="font-mono tabular-nums">{a.score}</span>
              {a.band && a.band !== 'unscored' && <Badge tone={a.band === 'hot' ? 'success' : a.band === 'disqualified' ? 'neutral' : 'info'} size="xs">{statusWord(a.band).label}</Badge>}
            </span>
          ) : 'Not scored yet'}
        </Field>
        <Field label="Phone" mono>{formatPhone(lead.phone)}</Field>
        <Field label="Email">{lead.email}</Field>
        <Field label="Updated">{fullDate(lead.updatedAt)}</Field>
      </dl>
      {lead.doNotCall && <Badge tone="warning" size="xs">On the do-not-call list</Badge>}
      <div className="rounded-control bg-canvas p-3">
        <p className="text-meta font-medium text-fg-muted">Notes</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-ui text-fg-body">{lead.notes || 'No notes yet.'}</p>
      </div>
    </Block>
  );
}

const FACT_LABELS = {
  status: 'Status',
  requestedWhen: 'Asked for',
  resolvedWindow: 'Call window',
  dueAt: 'Will call',
  expiresAt: 'Expires',
  requestedAt: 'Requested',
  updatedAt: 'Last update',
  language: 'Language',
  originalLanguage: 'Call was in',
  requestText: 'What they said',
  handoffTo: 'Wants to hear from',
  handoffReason: 'Reason',
  app: 'App',
  startedAt: 'Started',
  completedAt: 'Finished',
  number: 'Phone line',
  addedAt: 'Added',
  agentName: 'Agent',
  amount: 'Amount',
  kindLabel: 'Type',
  at: 'Date',
  channelsBefore: 'Channels before',
  channelsAfter: 'Channels after',
  balance: 'Wallet balance',
  timezone: 'Time zone',
};
const DATE_FACTS = new Set(['dueAt', 'expiresAt', 'requestedAt', 'updatedAt', 'startedAt', 'completedAt', 'addedAt', 'at']);
const MONO_FACTS = new Set(['amount', 'balance', 'number', 'channelsBefore', 'channelsAfter']);

function Facts({ facts }) {
  const entries = Object.entries(facts || {}).filter(([k, v]) => FACT_LABELS[k] && v !== '' && v != null && k !== 'kind');
  if (!entries.length) return null;
  return (
    <Block title="Details">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        {entries.map(([k, v]) => (
          <Field key={k} label={FACT_LABELS[k]} mono={MONO_FACTS.has(k)}>
            {k === 'status' ? <StatusBadge status={v} size="xs" /> : DATE_FACTS.has(k) ? fullDate(v) : String(v)}
          </Field>
        ))}
      </dl>
    </Block>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4 px-5 py-4 sm:px-6" aria-busy="true" aria-label="Loading details">
      <div className="grid grid-cols-2 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-4 w-28" />
          </div>
        ))}
      </div>
      <Skeleton className="h-20 w-full rounded-control" />
      <Skeleton className="h-12 w-4/5 rounded-control" />
      <Skeleton className="ml-auto h-12 w-3/4 rounded-control" />
    </div>
  );
}

/** Where the panel's "Open in …" buttons go, by item type. */
function navTargets(item, detail) {
  const { callId, leadId, campaignId } = itemTargets(item, detail);
  const out = [];
  const t = item.type || '';
  if (callId && !t.startsWith('lead.')) out.push({ kind: 'nav_call', label: t === 'call.live' ? 'Open live call' : 'Open in Calls', callId });
  if (leadId) out.push({ kind: 'nav_lead', label: 'Open lead', leadId, name: detail?.lead?.name || item.contact?.name || '' });
  if (campaignId) out.push({ kind: 'nav_campaign', label: 'Open campaign', campaignId });
  if (t.startsWith('followup.') || t === 'callback.due') out.push({ kind: 'open_followups', label: 'Open follow-ups' });
  if (t.startsWith('callback.')) out.push({ kind: 'open_callbacks', label: 'Open callbacks' });
  if (t.startsWith('language.')) out.push({ kind: 'open_language', label: 'Open language callbacks' });
  if (t.startsWith('billing.') || t.startsWith('channel.')) out.push({ kind: 'open_billing', label: 'Open billing' });
  if (t.startsWith('number.')) out.push({ kind: 'open_numbers', label: 'Open phone lines' });
  if (t.startsWith('integration.')) out.push({ kind: 'open_integrations', label: 'Open integrations' });
  return out;
}

const NAV_KINDS = new Set(['open_call', 'open_calls', 'open_lead', 'open_campaign', 'open_followups', 'open_callbacks', 'open_language', 'open_billing', 'open_numbers', 'open_integrations']);

/**
 * Everything about one feed item, in a drawer on the right (a full-height sheet on
 * phones). Esc closes; focus is trapped and restored; ↑/↓ move to the previous or
 * next item while open. `suspended` pauses the keyboard handling and focus trap
 * while a confirm dialog is open on top.
 */
export function ItemDetailPanel({
  itemId,
  item: listedItem,
  position,
  total,
  onPrev,
  onNext,
  onClose,
  onAction,
  onNavigateTo,
  onOpenItem,
  busyAction,
  agentNames,
  now,
  suspended = false,
  refreshKey = 0,
}) {
  const open = Boolean(itemId);
  const panel = useRef(null);
  const restore = useRef(null);
  const titleId = useId();
  const phone = useIsPhone();
  const detail = useItemDetail(itemId, refreshKey);
  const item = detail.data?.item || listedItem;
  const keys = useRef({});
  keys.current = { onClose, onPrev, onNext, suspended };

  // Remember what had focus, focus the panel, restore on close.
  useEffect(() => {
    if (!open) return undefined;
    restore.current = document.activeElement;
    panel.current?.focus({ preventScroll: true });
    const frame = requestAnimationFrame(() => {
      if (!panel.current?.contains(document.activeElement)) panel.current?.focus({ preventScroll: true });
    });
    return () => {
      cancelAnimationFrame(frame);
      const node = restore.current;
      if (node?.isConnected) node.focus({ preventScroll: true });
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      const k = keys.current;
      if (k.suspended || event.defaultPrevented) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        k.onClose();
        return;
      }
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !event.altKey && !event.metaKey && !event.ctrlKey) {
        const tag = event.target?.tagName;
        if (['INPUT', 'TEXTAREA', 'SELECT', 'AUDIO'].includes(tag) || event.target?.isContentEditable) return;
        event.preventDefault();
        (event.key === 'ArrowDown' ? k.onNext : k.onPrev)?.();
        return;
      }
      if (event.key === 'Tab' && panel.current) {
        const nodes = [...panel.current.querySelectorAll(FOCUSABLE)].filter((n) => n.getClientRects().length);
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        const inside = panel.current.contains(document.activeElement);
        if (!first) { event.preventDefault(); panel.current.focus(); }
        else if (event.shiftKey && (!inside || document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (!inside || document.activeElement === last)) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  // Moving between items starts the new one at the top.
  const body = useRef(null);
  useEffect(() => { body.current?.scrollTo?.({ top: 0 }); }, [itemId]);

  const data = detail.data;
  const actions = (item?.actions || []).filter((a) => !NAV_KINDS.has(a.kind));
  const mainActions = actions.filter((a) => PRIMARY_KINDS.has(a.kind));
  const otherActions = actions.filter((a) => !PRIMARY_KINDS.has(a.kind));
  const nav = item ? navTargets(item, data) : [];
  const call = data?.call;
  const related = data?.related || {};
  const callIsSource = call && !(item?.type || '').startsWith('call.');
  const agentName = item ? agentNames[item.agentId] : '';
  const live = item?.type === 'call.live' || call?.in_progress;
  const hasRecording = call?.has_recording || (item?.actions || []).some((a) => a.kind === 'play_recording');

  const sheet = phone
    ? { initial: { y: '100%' }, animate: { y: 0 }, exit: { y: '100%' } }
    : { initial: { x: '100%' }, animate: { x: 0 }, exit: { x: '100%' } };

  if (typeof document === 'undefined') return null;
  // Portalled to <body>: the panel overlays the whole console, outside the page's spacing and stacking.
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40" data-testid="home-item-detail-layer">
          <motion.div
            className="absolute inset-0 bg-ink/25"
            aria-hidden="true"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2, ease: EASE_OUT } }}
            exit={{ opacity: 0, transition: { duration: 0.15 } }}
          />
          <motion.aside
            ref={panel}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            data-testid="home-item-detail"
            {...sheet}
            transition={drawerSpring}
            className={`absolute flex flex-col overflow-hidden bg-surface shadow-craft-lg focus:outline-none ${
              phone
                ? 'inset-x-0 bottom-0 top-3 rounded-t-card border-t border-line'
                : 'inset-y-0 right-0 w-full max-w-[480px] border-l border-line xl:max-w-[520px]'
            }`}
          >
            {phone && <div aria-hidden="true" className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-pill bg-line-strong" />}
            <header className="flex shrink-0 items-center justify-between gap-2 px-5 pt-3 pb-2 sm:px-6 sm:pt-4">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={onPrev}
                  disabled={!onPrev}
                  aria-label="Previous item"
                  title="Previous (↑)"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-control text-fg-body hover:bg-canvas hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40"
                >
                  <ChevronUp className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={onNext}
                  disabled={!onNext}
                  aria-label="Next item"
                  title="Next (↓)"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-control text-fg-body hover:bg-canvas hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
                {position > 0 && total > 0 && (
                  <span className="ml-1 font-mono text-meta tabular-nums text-fg-muted">{position} of {total}</span>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close details"
                className="inline-flex h-11 w-11 items-center justify-center rounded-control text-fg-muted hover:bg-canvas hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:h-9 sm:w-9"
                data-testid="home-item-detail-close"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div ref={body} className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)]">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={itemId}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0, transition: { duration: 0.18, ease: EASE_OUT } }}
                  exit={{ opacity: 0, transition: { duration: 0.1 } }}
                >
                  {item ? (
                    <div className="flex items-start gap-3 px-5 pb-4 sm:px-6">
                      <ItemAvatar item={item} agentName={agentName} size="md" />
                      <div className="min-w-0 flex-1">
                        <h2 id={titleId} className="text-title text-ink break-words">
                          <ItemSentence item={item} />
                        </h2>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-meta text-fg-muted">
                          {item.type === 'call.live' ? (
                            <Badge tone="live" dot size="xs">On a call</Badge>
                          ) : (
                            <time dateTime={item.at} title={fullDate(item.at) || undefined}>{relativeTime(item.at, now)}</time>
                          )}
                          {!item.actor && agentName && <span>· {agentName}</span>}
                          {item.meta?.outcome && <Badge tone={item.tone === 'success' ? 'success' : 'neutral'} size="xs">{item.meta.outcome}</Badge>}
                          {item.needsAction && <Badge tone={item.tone === 'danger' ? 'danger' : 'warning'} size="xs">Needs you</Badge>}
                        </div>
                        {item.detail && <p className="mt-2 text-ui text-fg-body break-words">{item.detail}</p>}
                      </div>
                    </div>
                  ) : (
                    <h2 id={titleId} className="px-5 pb-4 text-title text-ink sm:px-6">Activity</h2>
                  )}

                  {item && (mainActions.length > 0 || otherActions.length > 0 || nav.length > 0) && (
                    <div className="flex flex-wrap items-center gap-2 px-5 pb-4 sm:px-6" data-testid="home-item-detail-actions">
                      {mainActions.map((action, index) => (
                        <TactileButton
                          key={`${action.kind}-${index}`}
                          size="sm"
                          variant={index === 0 && item.needsAction ? 'primary' : 'secondary'}
                          loading={busyAction === `${item.id}:${action.kind}`}
                          onClick={() => onAction(item, action)}
                        >
                          {action.label}
                        </TactileButton>
                      ))}
                      {otherActions.map((action, index) => (
                        <TactileButton
                          key={`${action.kind}-o-${index}`}
                          size="sm"
                          variant="ghost"
                          loading={busyAction === `${item.id}:${action.kind}`}
                          onClick={() => onAction(item, action)}
                        >
                          {action.label}
                        </TactileButton>
                      ))}
                      {nav.map((target) => (
                        <TactileButton key={target.kind} size="sm" variant="secondary" icon={ArrowUpRight} onClick={() => onNavigateTo(item, target)}>
                          {target.label}
                        </TactileButton>
                      ))}
                    </div>
                  )}

                  {detail.error ? (
                    <p role="status" className="mx-5 mb-4 rounded-control bg-warning-soft p-3 text-ui text-warning-fg sm:mx-6">{detail.error}</p>
                  ) : !data ? (
                    <DetailSkeleton />
                  ) : (
                    <>
                      {data.lead && <LeadBlock lead={data.lead} />}
                      {data.campaign && <CampaignBlock campaign={data.campaign} />}
                      <Facts facts={data.facts} />
                      {call && <CallBlock call={call} item={item} now={now} title={callIsSource ? 'Source call' : 'Call'} />}
                      {call && hasRecording && call.connected !== false && (
                        <Block title="Recording" icon={Headphones}><Recording callId={call.call_id} /></Block>
                      )}
                      {call && call.connected !== false && (
                        <Block title={live ? 'Live transcript' : 'Transcript'} icon={MessageSquareText}>
                          <Transcript callId={call.call_id} agentName={call.agent_name} live={Boolean(live)} />
                        </Block>
                      )}
                      {related.integrationActions?.length > 0 && (
                        <Block title="Done in your apps during the call">
                          <RelatedList items={related.integrationActions} agentNames={agentNames} now={now} onOpenItem={onOpenItem} />
                        </Block>
                      )}
                      {(related.callbacks?.length > 0 || related.followUps?.length > 0 || related.languageRequests?.length > 0) && (
                        <Block title="Callbacks and follow-ups">
                          <RelatedList
                            items={[...(related.callbacks || []), ...(related.followUps || []), ...(related.languageRequests || [])]}
                            agentNames={agentNames}
                            now={now}
                            onOpenItem={onOpenItem}
                          />
                        </Block>
                      )}
                      {data.lead && (
                        <Block title="Last calls">
                          {related.calls?.length ? (
                            <RelatedList items={related.calls} agentNames={agentNames} now={now} onOpenItem={onOpenItem} />
                          ) : (
                            <p className="text-ui text-fg-muted">No calls linked to this lead yet.</p>
                          )}
                        </Block>
                      )}
                      <div className="h-4" />
                    </>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
            <p className="hidden shrink-0 border-t border-line px-6 py-2 text-meta text-fg-muted sm:block">
              <kbd className="font-mono">↑</kbd> <kbd className="font-mono">↓</kbd> to move between items · <kbd className="font-mono">Esc</kbd> to close
            </p>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
