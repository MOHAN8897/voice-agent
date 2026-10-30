import React from 'react';

/**
 * PageHeader — top of every console page.
 *
 *   <PageHeader title="Calls" description="Every call your agents made or took."
 *     actions={<Button>New call</Button>} />
 *
 * Title: sentence case, 20–24px. Description: one plain sentence. `eyebrow` is an
 * optional short sentence-case context line (never all caps). Actions wrap under
 * the title on phones.
 */
export function PageHeader({ title, description = null, eyebrow = null, actions = null, className = '', children = null }) {
  return (
    <header className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-ui font-medium text-fg-muted">{eyebrow}</div>}
        <h1 className="text-heading sm:text-display text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-copy text-fg-body">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{actions}</div>}
    </header>
  );
}
