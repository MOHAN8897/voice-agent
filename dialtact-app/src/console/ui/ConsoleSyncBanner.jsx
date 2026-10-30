import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useWorkspace } from '../context/WorkspaceContext';
import { TactileButton } from './TactileButton';

export function ConsoleSyncBanner() {
  const { syncError, syncPartialErrors, isLoading, loadWorkspaceData } = useWorkspace();
  const issues = syncError
    ? [syncError]
    : syncPartialErrors?.length
      ? syncPartialErrors
      : null;

  if (!issues?.length) return null;

  return (
    <div
      className="mb-4 rounded-card border border-warning-line bg-warning-soft px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
      role="status"
    >
      <div className="flex min-w-0 gap-2.5 text-copy text-warning-fg">
        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-warning-fg" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-semibold">Some information could not be loaded</p>
          <ul className="mt-1 text-ui text-warning-fg list-disc pl-4 space-y-0.5 break-words">
            {[...new Set(issues)].slice(0, 4).map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
            {issues.length > 4 && <li>…and {issues.length - 4} more</li>}
          </ul>
        </div>
      </div>
      <TactileButton
        variant="secondary"
        size="sm"
        icon={RefreshCw}
        onClick={() => loadWorkspaceData()}
        disabled={isLoading}
      >
        Retry sync
      </TactileButton>
    </div>
  );
}
