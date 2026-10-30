import React, { useRef } from 'react';

/**
 * Tabs — a segmented control for switching views or filters on one page.
 *
 *   <Tabs value={range} onChange={setRange} label="Time range"
 *     items={[{ id: 'today', label: 'Today' }, { id: '7d', label: '7 days', count: 12 }]} />
 *
 * Keyboard: arrow keys move between tabs. `variant="pills"` scrolls horizontally on
 * phones and wraps on wider screens, so no filter is ever clipped (good for filter rows).
 */
export function Tabs({ items, value, onChange, label, className = '', variant = 'segmented', size = 'md' }) {
  const refs = useRef([]);
  const onKeyDown = (event, index) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    refs.current[next]?.focus();
    onChange(items[next].id);
  };
  const pills = variant === 'pills';
  return (
    <div
      role="tablist"
      aria-label={label}
      className={
        pills
          ? `relative flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 sm:flex-wrap sm:overflow-visible ${className}`
          : `inline-flex items-center gap-0.5 rounded-control border border-line bg-surface-subtle p-0.5 ${className}`
      }
    >
      {items.map((item, index) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            ref={(node) => { refs.current[index] = node; }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onKeyDown={(event) => onKeyDown(event, index)}
            onClick={() => onChange(item.id)}
            className={
              pills
                ? `shrink-0 inline-flex items-center gap-1.5 rounded-pill border px-3 ${size === 'sm' ? 'py-1' : 'py-1.5 min-h-[36px]'} text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    active ? 'border-ink bg-ink text-white' : 'border-line bg-surface text-fg-body hover:border-line-strong hover:text-ink'
                  }`
                : `inline-flex items-center gap-1.5 rounded-[8px] px-3 ${size === 'sm' ? 'py-1' : 'py-1.5 min-h-[32px]'} text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    active ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
                  }`
            }
          >
            {item.label}
            {item.count != null && item.count > 0 && (
              <span className={`rounded-pill px-1.5 text-meta font-mono tabular-nums ${active ? (pills ? 'bg-white/20 text-white' : 'bg-surface-subtle text-ink') : 'bg-surface-subtle text-fg-body'}`}>
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
