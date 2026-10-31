import React, { forwardRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Blocks,
  CalendarClock,
  ChevronRight,
  CreditCard,
  Languages,
  Layers,
  Megaphone,
  Phone,
  PhoneCall,
  PhoneMissed,
  ShieldOff,
  TriangleAlert,
  UserPlus,
  Wallet,
} from 'lucide-react';
import { Avatar } from '../../ui/Avatar';
import { Badge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { LanguageTag } from '../../ui/LanguageTag';
import { formatClock, relativeTime } from '../../../lib/money';
import { rowTransition, rowVariants } from './motion';

const TONE_BAR = {
  danger: 'before:bg-danger',
  warning: 'before:bg-warning',
};

export function iconFor(type = '') {
  if (type.startsWith('billing.')) return Wallet;
  if (type.startsWith('number.')) return Phone;
  if (type.startsWith('channel.')) return Layers;
  if (type.startsWith('integration.')) return Blocks;
  if (type.startsWith('campaign.')) return Megaphone;
  if (type.startsWith('lead.')) return UserPlus;
  if (type === 'call.missed') return PhoneMissed;
  if (type === 'call.technical') return TriangleAlert;
  if (type === 'call.dnd') return ShieldOff;
  if (type.startsWith('language.')) return Languages;
  if (type.startsWith('followup.') || type === 'callback.due') return CalendarClock;
  if (type.startsWith('callback.')) return PhoneCall;
  if (type.startsWith('wallet')) return CreditCard;
  return PhoneCall;
}

/** Which actions render as buttons; the rest go in a quieter "more" row. */
export const PRIMARY_KINDS = new Set([
  'call_back', 'call_in_language', 'approve_followup', 'top_up', 'reconnect_integration', 'play_recording',
]);

/** The avatar a row (or the detail panel) shows: the agent, or an icon for system items. */
export function ItemAvatar({ item, agentName, size = 'sm' }) {
  const actor = item.actor || null;
  const live = item.type === 'call.live';
  if (actor || (item.agentId && agentName && !item.type.startsWith('call.missed'))) {
    return <Avatar name={actor || agentName} size={size} live={live} title={actor || agentName} />;
  }
  return <Avatar icon={iconFor(item.type)} tone={item.tone === 'live' ? 'live' : item.tone} size={size} />;
}

/** "Meera booked a site visit with Ravi" — actor bold, the rest as body text. */
export function ItemSentence({ item, className = '' }) {
  const actor = item.actor || null;
  return (
    <span className={className}>
      {actor && <span className="font-semibold text-ink">{actor} </span>}
      <span className={actor ? 'text-fg-body' : 'font-medium text-ink'}>{item.text}</span>
    </span>
  );
}

/**
 * The language a caller asked for, and the language a callback was placed in.
 * Language callbacks carry it on every status; calls carry it when the caller
 * asked for another language or the call was a language callback.
 */
export function ItemLanguageTags({ item }) {
  const meta = item.meta || {};
  const type = item.type || '';
  const tags = [];
  if (meta.language) {
    const prefix = type === 'language.calling' ? 'Calling in' : type === 'language.done' ? 'Called in' : 'Wants';
    tags.push(<LanguageTag key="wants" code={meta.language} label={meta.languageLabel} prefix={prefix} />);
  }
  if (meta.callLanguage && meta.callLanguage !== meta.language) {
    tags.push(<LanguageTag key="call" code={meta.callLanguage} label={meta.callLanguageLabel} prefix="Called in" />);
  }
  return tags.length ? <>{tags}</> : null;
}

/**
 * One feed row: who (avatar), what happened (one plain sentence), when, and what
 * you can do about it. The whole row opens the detail panel; the inline action
 * buttons keep working on their own. `now` drives live timers so every row ticks
 * together.
 */
export const FeedItem = forwardRef(function FeedItem(
  { item, agentName, now, fresh = false, busyAction = null, onAction, onOpen, selected = false, animate = true },
  ref
) {
  const [expanded, setExpanded] = useState(false);
  const live = item.type === 'call.live';
  const actor = item.actor || null;
  const startedAt = item.meta?.startedAt || item.at;
  const elapsed = live && startedAt ? (now - new Date(startedAt).getTime()) / 1000 : 0;
  const actions = item.actions || [];
  const mainActions = actions.filter((a) => PRIMARY_KINDS.has(a.kind)).slice(0, 2);
  const linkActions = actions.filter((a) => !mainActions.includes(a)).slice(0, 3);
  const outcome = item.meta?.outcome;
  const duration = item.meta?.duration;
  const dueAt = item.meta?.dueAt;
  const longDetail = (item.detail || '').length > 110;

  const openFromRow = (event) => {
    if (!onOpen) return;
    // Inline actions, links and the summary toggle keep their own behaviour.
    if (event.target.closest('[data-row-action]')) return;
    // Selecting text to copy it is not a click.
    if (typeof window !== 'undefined' && String(window.getSelection?.() || '').trim()) return;
    onOpen(item);
  };

  const Row = animate ? motion.li : 'li';
  const motionProps = animate
    ? {
        layout: 'position',
        variants: rowVariants,
        initial: fresh ? 'initial' : false,
        animate: 'animate',
        exit: 'exit',
        transition: { layout: rowTransition },
      }
    : {};

  return (
    <Row
      ref={ref}
      {...motionProps}
      onClick={openFromRow}
      className={`group relative flex cursor-pointer gap-3 px-4 py-3.5 sm:px-5 transition-colors duration-150 before:absolute before:left-0 before:top-3 before:bottom-3 before:w-[3px] before:rounded-r-full ${
        TONE_BAR[item.tone] || 'before:bg-transparent'
      } ${selected ? 'bg-accent-soft/60' : 'hover:bg-canvas active:bg-surface-subtle/70'}`}
      data-testid="feed-item"
      data-type={item.type}
      data-item-id={item.id}
      aria-current={selected ? 'true' : undefined}
    >
      <ItemAvatar item={item} agentName={agentName} />

      <div className="min-w-0 flex-1">
        <p className="text-copy break-words">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpen?.(item);
            }}
            className="rounded-[4px] text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
            aria-label={`${actor ? `${actor} ` : ''}${item.text}. Open details`}
            data-testid="feed-item-open"
          >
            <ItemSentence item={item} />
          </button>
          {live && (
            <span className="ml-1.5 inline-flex items-center gap-1 font-mono tabular-nums text-success-fg" aria-label={`for ${formatClock(elapsed)}`}>
              <span aria-hidden="true" className="relative inline-flex h-1.5 w-1.5">
                <span className="absolute inset-0 rounded-full bg-success opacity-60 motion-safe:animate-ping" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
              </span>
              {formatClock(elapsed)}
            </span>
          )}
        </p>
        {item.detail && (
          <div className="mt-0.5 flex items-start gap-1">
            <p className={`min-w-0 text-ui text-fg-muted break-words ${expanded ? '' : 'line-clamp-1'}`}>{item.detail}</p>
            {longDetail && (
              <button
                type="button"
                data-row-action
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
                className="shrink-0 rounded-[4px] text-ui font-medium text-accent-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {expanded ? 'Less' : 'More'}
              </button>
            )}
          </div>
        )}

        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-meta text-fg-muted">
          {live ? (
            <Badge tone="live" dot size="xs">On a call</Badge>
          ) : (
            <time dateTime={item.at} title={item.at ? new Date(item.at).toLocaleString('en-IN') : undefined}>
              {relativeTime(item.at, now)}
            </time>
          )}
          {!actor && agentName && <span>· {agentName}</span>}
          {duration && <span className="font-mono tabular-nums">· {duration}</span>}
          {dueAt && <span>· due {relativeTime(dueAt, now)}</span>}
          {outcome && <Badge tone={item.tone === 'success' ? 'success' : 'neutral'} size="xs">{outcome}</Badge>}
          <ItemLanguageTags item={item} />
          {item.needsAction && <Badge tone={item.tone === 'danger' ? 'danger' : 'warning'} size="xs">Needs you</Badge>}
        </div>

        {(mainActions.length > 0 || linkActions.length > 0) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2" data-row-action>
            {mainActions.map((action, index) => (
              <TactileButton
                key={`${action.kind}-${index}`}
                size="xs"
                variant={index === 0 && item.needsAction ? 'primary' : 'secondary'}
                loading={busyAction === `${item.id}:${action.kind}`}
                onClick={() => onAction(item, action)}
                className="min-h-[36px] sm:min-h-0"
              >
                {action.label}
              </TactileButton>
            ))}
            {linkActions.map((action, index) => (
              <button
                key={`${action.kind}-link-${index}`}
                type="button"
                onClick={() => onAction(item, action)}
                disabled={busyAction === `${item.id}:${action.kind}`}
                className="min-h-[36px] sm:min-h-0 rounded-control px-1.5 text-ui font-medium text-accent-fg hover:text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <ChevronRight
        aria-hidden="true"
        className={`mt-1 hidden h-4 w-4 shrink-0 text-fg-subtle transition-[opacity,transform] duration-150 sm:block ${
          selected ? 'translate-x-0.5 opacity-100' : 'opacity-0 group-hover:translate-x-0.5 group-hover:opacity-100'
        }`}
      />
    </Row>
  );
});
