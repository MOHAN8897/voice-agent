import React, { useState } from 'react';

/**
 * Plain CSS charts for analytics (no chart library). One hue (accent) for magnitude;
 * every value is printed as text beside its bar, so colour never carries meaning
 * alone, and each bar has a hover/focus tooltip through `title`.
 */

/** Horizontal bars: one row per category, value printed at the end. */
export function BarList({ rows, format = (v) => v.toLocaleString('en-IN'), empty = 'Nothing in this period.', label, testId }) {
  const max = Math.max(0, ...rows.map((r) => r.value));
  if (!rows.length || max === 0) {
    return <p className="text-ui text-fg-muted">{empty}</p>;
  }
  return (
    <ul className="space-y-2.5" aria-label={label} data-testid={testId}>
      {rows.map((row) => {
        const pct = max ? Math.max(row.value > 0 ? 2 : 0, (row.value / max) * 100) : 0;
        return (
          <li key={row.key ?? row.label} className="min-w-0" title={`${row.label}: ${format(row.value)}`}>
            <div className="flex items-baseline justify-between gap-3 text-ui">
              <span className="min-w-0 truncate text-fg-body">{row.label}</span>
              <span className="shrink-0 font-mono tabular-nums text-ink">
                {format(row.value)}
                {row.hint && <span className="ml-1.5 font-sans text-meta text-fg-muted">{row.hint}</span>}
              </span>
            </div>
            <div className="mt-1 h-2 rounded-pill bg-surface-subtle" aria-hidden="true">
              <div className="h-2 rounded-pill bg-accent" style={{ width: `${pct}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function shortDay(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

/**
 * Vertical day bars with a table view. `series` is the one value to plot; an
 * optional `secondary` key is listed in the tooltip and table, not drawn, so the
 * chart never needs a second axis.
 */
export function DayBars({ data, valueKey, label, format = (v) => v.toLocaleString('en-IN'), secondary = null, testId }) {
  const [table, setTable] = useState(false);
  const max = Math.max(0, ...data.map((d) => d[valueKey] || 0));
  const step = Math.ceil(data.length / 8);
  return (
    <figure className="min-w-0" data-testid={testId}>
      <div className="mb-2 flex justify-end">
        <button
          type="button"
          onClick={() => setTable((v) => !v)}
          className="rounded-control px-2 py-1 text-meta font-medium text-accent-fg hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-pressed={table}
        >
          {table ? 'Show chart' : 'Show table'}
        </button>
      </div>
      {table ? (
        <div className="max-h-64 overflow-auto rounded-control border border-line">
          <table className="w-full text-ui">
            <caption className="sr-only">{label}</caption>
            <thead className="bg-surface-subtle text-meta text-fg-muted">
              <tr>
                <th scope="col" className="px-3 py-1.5 text-left font-medium">Day</th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">{label}</th>
                {secondary && <th scope="col" className="px-3 py-1.5 text-right font-medium">{secondary.label}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((d) => (
                <tr key={d.date}>
                  <td className="px-3 py-1.5 text-fg-body">{shortDay(d.date)}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-ink">{format(d[valueKey] || 0)}</td>
                  {secondary && <td className="px-3 py-1.5 text-right font-mono tabular-nums text-ink">{(d[secondary.key] || 0).toLocaleString('en-IN')}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : max === 0 ? (
        <p className="py-8 text-center text-ui text-fg-muted">Nothing in this period.</p>
      ) : (
        <>
          <div className="flex h-40 items-end gap-[2px] border-b border-line" role="list" aria-label={label}>
            {data.map((d) => {
              const value = d[valueKey] || 0;
              const tip = `${shortDay(d.date)}: ${format(value)}${secondary ? ` · ${secondary.label} ${(d[secondary.key] || 0).toLocaleString('en-IN')}` : ''}`;
              return (
                <div key={d.date} role="listitem" tabIndex={0} title={tip} aria-label={tip}
                  className="group flex h-full min-w-0 flex-1 items-end justify-center rounded-t-[4px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
                  <div
                    className="w-full max-w-[32px] rounded-t-[4px] bg-accent opacity-90 transition-opacity group-hover:opacity-100"
                    style={{ height: `${value ? Math.max(2, (value / max) * 100) : 0}%` }}
                  />
                </div>
              );
            })}
          </div>
          <div className="mt-1 flex gap-[2px]" aria-hidden="true">
            {data.map((d, i) => (
              <span key={d.date} className="min-w-0 flex-1 truncate text-center text-meta text-fg-muted">
                {i % step === 0 ? shortDay(d.date) : ''}
              </span>
            ))}
          </div>
          <figcaption className="sr-only">{label} per day. Use “Show table” for the numbers.</figcaption>
        </>
      )}
    </figure>
  );
}
