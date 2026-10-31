import React from 'react';

/**
 * EmptyState — what a list shows when it has nothing yet. Say what will appear
 * here and offer the one action that makes it appear.
 *
 *   <EmptyState icon={PhoneCall} title="No calls yet"
 *     description="Calls your agents make or take will show up here."
 *     action={<Button>Place a test call</Button>} />
 */
export function EmptyState({ icon: Icon = null, title, description = null, action = null, className = '', compact = false }) {
  return (
    <div className={`flex flex-col items-center text-center ${compact ? 'py-6 px-4' : 'py-12 px-6'} ${className}`}>
      {Icon && (
        <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-control bg-surface-subtle" aria-hidden="true">
          <Icon className="h-5 w-5 text-fg-body" />
        </span>
      )}
      <p className="text-title text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-ui text-fg-muted">{description}</p>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
