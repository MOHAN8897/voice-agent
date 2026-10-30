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
      className="shrink-0 border-b border-rose-300 bg-rose-50 px-4 py-2.5 text-xs text-rose-950 font-medium"
      data-testid="grace-period-banner"
      role="alert"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>
            This workspace is quarantined and scheduled for permanent deletion on{' '}
            <strong>{purgeDateStr}</strong>.
            {msg && <span className="ml-2 font-semibold text-rose-700">({msg})</span>}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={handleExport}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-800 hover:bg-rose-100 disabled:opacity-60 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Export data
          </button>
          {(user?.role === 'owner' || user?.role === 'customer_admin' || user?.role === 'platform_admin' || user?.isPlatformAdmin) && (
            <button
              type="button"
              disabled={busy}
              onClick={handleCancel}
              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-60 transition-colors shadow-sm"
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
