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
        message: detail.message || 'Some parts of the console are not responding right now. You are still signed in.',
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
      className="mb-4 rounded-card border border-info-line bg-info-soft px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-200"
      role="status"
    >
      <div className="flex min-w-0 gap-2.5 text-copy text-info-fg">
        <WifiOff className="w-4 h-4 shrink-0 mt-0.5 text-info-fg" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-semibold">Reconnecting…</p>
          <p className="text-ui text-info-fg mt-0.5">
            {degradedState.message} Your work is saved.
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
          className="min-w-[36px] min-h-[36px] flex items-center justify-center rounded-control text-info-fg hover:bg-surface/60 transition-colors"
          title="Dismiss notice"
          aria-label="Dismiss notice"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
