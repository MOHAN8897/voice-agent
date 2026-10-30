import React from 'react';
import { Avatar } from '../ui/Avatar';
import { Badge } from '../ui/StatusBadge';
import { relativeTime } from '../../lib/money';

const TONE_BAR = {
  danger: 'before:bg-danger',
  warning: 'before:bg-warning',
  info: 'before:bg-info',
};

/**
 * One queue row styled like the Home feed's "Needs you" items: who (avatar),
 * one plain sentence, a quieter detail line, when, and the inline actions.
 *
 *   <NeedsYouItem agentName="Meera" icon={PhoneCall} tone="warning"
 *     actor="+91 98765 43210" text="asked for a call back" detail="Tomorrow after 5"
 *     at={row.createdAt} needsYou actions={<Button…/>} />
 *
 * `leading` replaces the avatar column (e.g. a checkbox plus avatar).
 */
export function NeedsYouItem({
  agentName = '',
  icon = null,
  tone = 'warning',
  actor = null,
  actorClassName = '',
  text,
  detail = null,
  children = null,
  at = null,
  meta = null,
  needsYou = false,
  badges = null,
  actions = null,
  leading = null,
  className = '',
  ...props
}) {
  return (
    <li
      className={`relative flex gap-3 px-4 py-3.5 sm:px-5 before:absolute before:left-0 before:top-3 before:bottom-3 before:w-[3px] before:rounded-r-full ${
        needsYou ? TONE_BAR[tone] || 'before:bg-transparent' : 'before:bg-transparent'
      } ${className}`}
      {...props}
    >
      {leading}
      {agentName ? (
        <Avatar name={agentName} size="sm" title={agentName} />
      ) : icon ? (
        <Avatar icon={icon} tone={tone} size="sm" />
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="text-copy text-ink break-words">
          {actor && <span className={`font-semibold ${actorClassName}`}>{actor} </span>}
          <span className={actor ? 'text-fg-body' : ''}>{text}</span>
        </p>
        {detail && <p className="mt-0.5 text-ui text-fg-muted break-words">{detail}</p>}
        {children}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-meta text-fg-muted">
          {at && (
            <time dateTime={at} title={new Date(at).toLocaleString('en-IN')}>
              {relativeTime(at)}
            </time>
          )}
          {meta}
          {badges}
          {needsYou && <Badge tone={tone === 'danger' ? 'danger' : 'warning'} size="xs">Needs you</Badge>}
        </div>
        {actions && <div className="mt-2.5 flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </li>
  );
}
