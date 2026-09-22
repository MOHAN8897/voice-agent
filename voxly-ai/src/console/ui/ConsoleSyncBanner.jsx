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
      className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
      role="status"
    >
      <div className="flex gap-2.5 text-sm text-amber-950">
        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-700" />
        <div>
          <p className="font-semibold">Some console data could not be loaded from the API</p>
          <ul className="mt-1 text-xs text-amber-900/90 list-disc pl-4 space-y-0.5">
            {issues.slice(0, 4).map((msg) => (
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
