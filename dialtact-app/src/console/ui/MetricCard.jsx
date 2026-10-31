import React from 'react';
import { Badge } from './StatusBadge';

/**
 * MetricCard — one number with a sentence-case label.
 *
 * `trend` is optional. A signed value ("+12%") is coloured success when positive
 * and neutral otherwise; any other text is a neutral note. Never red: a metric
 * moving is not a problem by itself (DESIGN.md → Status colour rules).
 * `compact` renders a smaller tile for rails and summary strips.
 */
export function MetricCard({
  title,
  value,
  trend = null,
  trendLabel = null,
  icon: Icon = null,
  subtitle = null,
  className = '',
  compact = false,
  onClick = null,
}) {
  const isPositive = typeof trend === 'string' && trend.startsWith('+');
  const Tag = onClick ? 'button' : 'div';

  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick || undefined}
      className={`block w-full text-left bg-surface border border-line rounded-card shadow-craft-xs ${compact ? 'p-4' : 'p-5 sm:p-6'} ${onClick ? 'hover:border-line-strong transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent' : ''} ${className}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-ui font-medium text-fg-body">{title}</span>
        {Icon && (
          <span className="w-8 h-8 rounded-control bg-surface-subtle flex items-center justify-center" aria-hidden="true">
            <Icon className="w-4 h-4 text-fg-body" />
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-baseline gap-2">
        <span className={`${compact ? 'text-heading' : 'text-display sm:text-[28px]'} font-bold font-mono tabular-nums text-ink`}>
          {value}
        </span>
        {trend && (
          <Badge tone={isPositive ? 'success' : 'neutral'} size="xs">
            {trend}
          </Badge>
        )}
      </div>

      {(subtitle || trendLabel) && <div className="mt-1 text-meta text-fg-muted">{subtitle || trendLabel}</div>}
    </Tag>
  );
}
