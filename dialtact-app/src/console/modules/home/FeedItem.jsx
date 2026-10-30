import React from 'react';
import {
  Blocks,
  CalendarClock,
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
import { formatClock, relativeTime } from '../../../lib/money';

const TONE_BAR = {
  danger: 'before:bg-danger',
  warning: 'before:bg-warning',
};

function iconFor(type) {
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
const PRIMARY_KINDS = new Set([
  'call_back', 'call_in_language', 'approve_followup', 'top_up', 'reconnect_integration', 'play_recording',
]);

/**
 * One feed row: who (avatar), what happened (one plain sentence), when, and what
 * you can do about it. `now` drives live timers so every row ticks together.
 */
export function FeedItem({ item, agentName, now, fresh = false, busyAction = null, onAction }) {
  const live = item.type === 'call.live';
  const actor = item.actor || null;
  const startedAt = item.meta?.startedAt || item.at;
  const elapsed = live && startedAt ? (now - new Date(startedAt).getTime()) / 1000 : 0;
  const Icon = iconFor(item.type);
  const actions = item.actions || [];
  const mainActions = actions.filter((a) => PRIMARY_KINDS.has(a.kind)).slice(0, 2);
  const linkActions = actions.filter((a) => !mainActions.includes(a)).slice(0, 3);
  const outcome = item.meta?.outcome;
  const duration = item.meta?.duration;
  const dueAt = item.meta?.dueAt;

  return (
    <li
      className={`relative flex gap-3 px-4 py-3.5 sm:px-5 before:absolute before:left-0 before:top-3 before:bottom-3 before:w-[3px] before:rounded-r-full ${
        TONE_BAR[item.tone] || 'before:bg-transparent'
      } ${fresh ? 'feed-item-enter' : ''}`}
      data-testid="feed-item"
      data-type={item.type}
    >
      {actor || (item.agentId && agentName && !item.type.startsWith('call.missed')) ? (
        <Avatar name={actor || agentName} size="sm" live={live} title={actor || agentName} />
      ) : (
        <Avatar icon={Icon} tone={item.tone === 'live' ? 'live' : item.tone} size="sm" />
      )}

      <div className="min-w-0 flex-1">
        <p className="text-copy text-ink break-words">
          {actor && <span className="font-semibold">{actor} </span>}
          <span className={actor ? 'text-fg-body' : ''}>{item.text}</span>
          {live && (
            <span className="ml-1.5 font-mono tabular-nums text-success-fg" aria-label={`for ${formatClock(elapsed)}`}>
              · {formatClock(elapsed)}
            </span>
          )}
        </p>
        {item.detail && <p className="mt-0.5 text-ui text-fg-muted line-clamp-2 break-words">{item.detail}</p>}

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
          {item.needsAction && <Badge tone={item.tone === 'danger' ? 'danger' : 'warning'} size="xs">Needs you</Badge>}
        </div>

        {(mainActions.length > 0 || linkActions.length > 0) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
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
    </li>
  );
}
