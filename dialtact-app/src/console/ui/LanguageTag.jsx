import React from 'react';
import { Languages } from 'lucide-react';

const NAMES = {
  te: 'Telugu', hi: 'Hindi', ta: 'Tamil', kn: 'Kannada', ml: 'Malayalam', mr: 'Marathi',
  bn: 'Bengali', gu: 'Gujarati', pa: 'Punjabi', en: 'English', ur: 'Urdu', or: 'Odia', as: 'Assamese',
};

/** "hi-IN" → "Hindi". A label the server already resolved wins. */
export function languageLabel(code, label = '') {
  if (label) return label;
  const raw = String(code || '').trim();
  return NAMES[raw.split('-')[0].toLowerCase()] || raw;
}

/**
 * LanguageTag — the language a caller asked for (or a callback was placed in).
 *
 *   <LanguageTag code="hi-IN" />                  → [文A Hindi]
 *   <LanguageTag label="Hindi" prefix="Wants" />  → [文A Wants Hindi]
 */
export function LanguageTag({ code = '', label = '', prefix = '', className = '' }) {
  const name = languageLabel(code, label);
  if (!name) return null;
  return (
    <span
      data-testid="language-tag"
      data-language={code || undefined}
      title={`${prefix ? `${prefix} ` : ''}${name}`}
      className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-pill border border-accent-soft bg-accent-soft px-2 py-0.5 text-meta font-medium text-accent-fg ${className}`}
    >
      <Languages className="h-3 w-3" aria-hidden="true" />
      <span className="sr-only">Language: </span>{prefix ? `${prefix} ${name}` : name}
    </span>
  );
}
