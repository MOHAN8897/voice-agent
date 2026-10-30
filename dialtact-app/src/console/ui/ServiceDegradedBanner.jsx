import React, { useState, useEffect } from 'react';
import { WifiOff, RefreshCw, X } from 'lucide-react';
import { TactileButton } from './TactileButton';

/**
 * ServiceDegradedBanner
 * Displayed when backend services or network connection experience temporary issues.
 * Reassures the tenant that their session and edits are preserved, avoiding panic or unexpected logout.
 */
export function ServiceDegradedBanner() {
  const [degradedState, setDegradedState] = useState(null);
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    const onDegraded = (ev) => {
      const detail = ev?.detail || {};
      setDegradedState({
        message: detail.message || 'Background service connectivity is degraded. Your session is active.',
        at: Date.now(),
      });
    };

    const onRestored = () => {
      setDegradedState(null);
      setIsRetrying(false);
    };

    window.addEventListener('dialtact:service-degraded', onDegraded);
    window.addEventListener('dialtact:service-restored', onRestored);

    return () => {
      window.removeEventListener('dialtact:service-degraded', onDegraded);
      window.removeEventListener('dialtact:service-restored', onRestored);
    };
  }, []);

  if (!degradedState) return null;

  const handleRetry = async () => {
    setIsRetrying(true);
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        setDegradedState(null);
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('dialtact:service-restored'));
        }
      }
    } catch {
      // Still degraded
    } finally {
      setIsRetrying(false);
    }
  };

  return (
    <div
      className="mb-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-200"
      role="status"
    >
      <div className="flex gap-2.5 text-sm text-sky-950">
        <WifiOff className="w-4 h-4 shrink-0 mt-0.5 text-sky-700" />
        <div>
          <p className="font-semibold text-xs sm:text-sm">Connecting to backend services...</p>
          <p className="text-[11px] sm:text-xs text-sky-900/90 mt-0.5">
            {degradedState.message} Workspace and edits remain saved.
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <TactileButton
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          onClick={handleRetry}
          disabled={isRetrying}
        >
          {isRetrying ? 'Retrying…' : 'Retry connection'}
        </TactileButton>
        <button
          type="button"
          onClick={() => setDegradedState(null)}
          className="p-1 rounded-lg text-sky-700 hover:bg-sky-100 transition-colors"
          title="Dismiss notice"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
