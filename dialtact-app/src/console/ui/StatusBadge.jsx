import React from 'react';
import { statusWord } from '../../lib/internalLabels';

/**
 * Semantic tones. The only colours a status may use (DESIGN.md → Status colour rules):
 *   success — done, connected, live          warning — needs the owner's attention
 *   danger  — something is broken or failed  info    — a neutral fact worth noticing
 *   neutral — everything else                accent  — brand emphasis, never a status
 */
export const TONE_STYLES = {
  success: { pill: 'bg-success-soft text-success-fg border-success-line', dot: 'bg-success' },
  warning: { pill: 'bg-warning-soft text-warning-fg border-warning-line', dot: 'bg-warning' },
  danger: { pill: 'bg-danger-soft text-danger-fg border-danger-line', dot: 'bg-danger' },
  info: { pill: 'bg-info-soft text-info-fg border-info-line', dot: 'bg-info' },
  neutral: { pill: 'bg-neutral-soft text-neutral-fg border-neutral-line', dot: 'bg-neutral' },
  accent: { pill: 'bg-accent-soft text-accent-fg border-accent-soft', dot: 'bg-accent' },
  live: { pill: 'bg-success-soft text-success-fg border-success-line', dot: 'bg-success animate-pulse' },
};

/**
 * Badge — a small label with a semantic tone.
 *
 *   <Badge tone="warning">Needs review</Badge>
 *   <Badge tone="success" dot>Live</Badge>
 */
export function Badge({ tone = 'neutral', dot = false, size = 'sm', className = '', children, ...props }) {
  const style = TONE_STYLES[tone] || TONE_STYLES.neutral;
  const sizeClass = size === 'xs' ? 'px-1.5 py-0.5 text-meta' : 'px-2 py-0.5 text-meta font-medium';
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill border font-medium ${sizeClass} ${style.pill} ${className}`}
      {...props}
    >
      {dot && <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />}
      {children}
    </span>
  );
}

/**
 * StatusBadge / StatusPill — maps any internal status (agent, call, lead stage,
 * campaign, follow-up, number…) to plain words and the right tone via the shared
 * humanizer. Existing props (`status`, `size`, `className`) are unchanged; `tone`
 * and `label` override the mapping when a caller knows better.
 */
export function StatusBadge({ status, size = 'sm', className = '', tone = null, label = null, dot = true }) {
  const word = statusWord(status);
  const resolvedTone = tone || (String(status || '').toLowerCase() === 'in_progress' ? 'live' : word.tone);
  return (
    <Badge tone={resolvedTone} dot={dot} size={size} className={className}>
      {label || word.label}
    </Badge>
  );
}

export const StatusPill = StatusBadge;
