import React from 'react';
import { Search } from 'lucide-react';

/**
 * Toolbar — the filter row above a list: tabs or pills on the left, search and
 * selects on the right. Wraps on phones; never scrolls the page sideways.
 *
 *   <Toolbar>
 *     <Tabs variant="pills" … />
 *     <Toolbar.Spacer />
 *     <SearchInput value={q} onChange={setQ} placeholder="Search calls" />
 *     <SelectFilter label="Agent" value={a} onChange={setA} options={[…]} />
 *   </Toolbar>
 */
export function Toolbar({ children, className = '' }) {
  return <div className={`flex flex-wrap items-center gap-2 min-w-0 ${className}`}>{children}</div>;
}

Toolbar.Spacer = function ToolbarSpacer() {
  return <div className="hidden flex-1 sm:block" aria-hidden="true" />;
};

export function SearchInput({ value, onChange, placeholder = 'Search', label = null, className = '' }) {
  return (
    <label className={`relative flex min-w-0 items-center ${className}`}>
      <span className="sr-only">{label || placeholder}</span>
      <Search className="pointer-events-none absolute left-3 h-4 w-4 text-fg-subtle" aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 w-full min-w-0 rounded-control border border-line bg-surface pl-9 pr-3 text-base sm:text-ui text-ink placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
      />
    </label>
  );
}

export function SelectFilter({ label, value, onChange, options, className = '' }) {
  return (
    <label className={`inline-flex min-w-0 items-center gap-2 text-ui text-fg-body ${className}`}>
      <span className="sr-only sm:not-sr-only shrink-0">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 min-w-0 max-w-[14rem] rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
