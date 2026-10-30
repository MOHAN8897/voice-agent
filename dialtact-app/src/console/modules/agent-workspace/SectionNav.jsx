import React from 'react';

/** Local categories preserve mounted form state when switching sections. */
export function SectionNav({ label, items, value, onChange, variant = 'tabs' }) {
  if (variant === 'tiles') return (
    <nav aria-label={label} className={`grid grid-cols-2 gap-3 ${items.length === 5 ? 'xl:grid-cols-5' : 'xl:grid-cols-4'}`}>
      {items.map(([id, title, Icon, description]) => (
        <button key={id} type="button" aria-pressed={value === id} aria-label={title}
          onClick={() => onChange(id)} className={`min-w-0 rounded-2xl border p-4 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#6344E7] ${value === id ? 'border-[#6344E7] bg-[#F0EEF6]' : 'border-[#E4E2EB] bg-white hover:bg-[#FAF9FD]'}`}>
          {Icon && <Icon aria-hidden="true" className="mb-3 h-5 w-5 text-[#6344E7]" />}
          <span className="block text-sm font-semibold text-[#0F0E17]">{title}</span>
          <span className="mt-1 block text-xs leading-relaxed text-[#524E5E]">{description}</span>
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
