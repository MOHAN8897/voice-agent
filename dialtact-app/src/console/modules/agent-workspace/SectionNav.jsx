import React from 'react';

/** Local categories preserve mounted form state when switching sections. */
export function SectionNav({ label, items, value, onChange, variant = 'tabs' }) {
  if (variant === 'tiles') return (
    <nav aria-label={label} className={`grid grid-cols-2 gap-3 ${items.length === 5 ? 'xl:grid-cols-5' : 'xl:grid-cols-4'}`}>
      {items.map(([id, title, Icon, description]) => (
        <button key={id} type="button" aria-pressed={value === id} aria-label={title}
          onClick={() => onChange(id)} className={`min-w-0 rounded-card border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${value === id ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:border-line-strong hover:bg-canvas'}`}>
          {Icon && <Icon aria-hidden="true" className="mb-3 h-5 w-5 text-accent" />}
          <span className="block text-copy font-semibold text-ink">{title}</span>
          <span className="mt-1 block text-ui leading-relaxed text-fg-body">{description}</span>
        </button>
      ))}
    </nav>
  );
  return (
    <nav aria-label={label} className="console-section-nav">
      {items.map(([id, title]) => (
        <button key={id} type="button" aria-pressed={value === id}
          onClick={() => onChange(id)} className="console-section-button">
          {title}
        </button>
      ))}
    </nav>
  );
}
