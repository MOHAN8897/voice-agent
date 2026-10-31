import React, { useState } from 'react';
import { AlertTriangle, Download, RotateCcw } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';

/**
 * Sticky banner shown when the workspace is quarantined pending permanent deletion.
 * Allows workspace owners to cancel deletion during the grace period or download
 * a data export archive.
 */
export function GracePeriodBanner() {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  if (user?.tenantStatus !== 'quarantined') return null;

  const purgeDateStr = user?.scheduledPurgeAt
    ? new Date(user.scheduledPurgeAt).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'the scheduled date';

  const handleCancel = async () => {
    if (busy) return;
    setBusy(true);
    setMsg('');
    try {
      await api.tenant.cancelDelete();
      window.location.reload();
    } catch (err) {
      setMsg(err?.message || 'Could not cancel deletion.');
      setBusy(false);
    }
  };

  const handleExport = async () => {
    if (busy) return;
    setBusy(true);
    setMsg('');
    try {
      const res = await api.tenant.createExport();
      setMsg(res?.message || 'Export queued. Check back shortly.');
    } catch (err) {
      setMsg(err?.message || 'Could not initiate export.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="shrink-0 border-b border-danger-line bg-danger-soft px-4 py-2.5 text-ui text-danger-fg"
      data-testid="grace-period-banner"
      role="alert"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-danger-fg shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            This workspace will be permanently deleted on{' '}
            <strong className="font-semibold">{purgeDateStr}</strong>. You can still export your data or cancel the deletion.
            {msg && <span className="ml-2 font-semibold text-danger-fg">({msg})</span>}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={handleExport}
            className="inline-flex min-h-[36px] items-center gap-1.5 rounded-control border border-danger-line bg-surface px-3 py-1 text-ui font-semibold text-danger-fg hover:bg-danger-soft disabled:opacity-60 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Export data
          </button>
          {(user?.role === 'owner' || user?.role === 'customer_admin' || user?.role === 'platform_admin' || user?.isPlatformAdmin) && (
            <button
              type="button"
              disabled={busy}
              onClick={handleCancel}
              className="inline-flex min-h-[36px] items-center gap-1.5 rounded-control bg-danger-fg px-3 py-1 text-ui font-semibold text-white hover:bg-danger disabled:opacity-60 transition-colors shadow-craft-xs"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Cancel deletion
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
