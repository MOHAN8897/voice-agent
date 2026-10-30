import React, { useCallback, useEffect, useState } from 'react';
import { CalendarClock, Download, LogOut, RotateCcw, ShieldCheck } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { formatInr, formatUsd } from '../../lib/money';
import { Badge } from './StatusBadge';
import { SolidCard } from './SolidCard';
import { TactileButton } from './TactileButton';

/**
 * Shown instead of the console while the workspace is pending deletion.
 *
 * The owner sees what a restore brings back, the date it will be gone, and three
 * choices: restore, download the data, or leave the deletion in place and sign out.
 * Other members see why they cannot get in. Nothing else in the console mounts, so no
 * other request runs against a workspace the server refuses.
 */

function formatDate(iso) {
  if (!iso) return 'the scheduled date';
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  } catch {
    return 'the scheduled date';
  }
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function walletLine(preview) {
  const inr = Number(preview?.walletBalanceInr) || 0;
  const usd = Number(preview?.walletBalanceUsd) || 0;
  if (inr > 0 && usd > 0) return `${formatInr(inr)} and ${formatUsd(usd)} wallet balance`;
  if (inr > 0) return `${formatInr(inr)} wallet balance`;
  if (usd > 0) return `${formatUsd(usd)} wallet balance`;
  return 'Your wallet and billing history';
}

export function WorkspaceRestoreScreen() {
  const { user, refreshSession, logout } = useAuth();
  const [status, setStatus] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(''); // '' | 'restore' | 'export' | 'leave'
  const [error, setError] = useState('');
  const [exportNote, setExportNote] = useState('');
  const [needsPassword, setNeedsPassword] = useState(false);

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const data = await api.tenant.getRestoreStatus();
      setStatus(data);
      setNeedsPassword(Boolean(data?.reauthRequired));
      if (data?.status === 'active') {
        await refreshSession();
      }
    } catch (err) {
      setLoadError(err?.message || 'We could not load this workspace.');
    }
  }, [refreshSession]);

  useEffect(() => {
    load();
  }, [load]);

  const workspaceName = status?.tenantName || user?.tenantName || 'This workspace';
  const purgeDate = formatDate(status?.scheduledPurgeAt || user?.scheduledPurgeAt);
  const preview = status?.restorePreview || {};
  const canRestore = Boolean(status?.canRestore);
  const blocked = status?.restoreBlockedReason;
  const hasPassword = status?.hasPassword !== false;

  const handleRestore = async (event) => {
    event?.preventDefault?.();
    if (busy) return;
    setBusy('restore');
    setError('');
    try {
      await api.tenant.restoreWorkspace({ currentPassword: needsPassword ? password : undefined });
      setPassword('');
      // Re-read the session: tenantStatus flips to active and the console takes over.
      await refreshSession();
      window.location.hash = '#dashboard/overview';
    } catch (err) {
      const code = err?.code || err?.message;
      if (code === 'reauth_required') {
        setNeedsPassword(true);
        setError(
          hasPassword
            ? 'For your security, enter your password to restore this workspace.'
            : 'For your security, sign out and sign in again with Google, then restore.'
        );
      } else if (code === 'invalid_credentials') {
        setError('That password is not right. Try again.');
      } else if (code === 'grace_period_expired' || code === 'workspace_deleted') {
        setError('The grace period has ended, so this workspace can no longer be restored.');
      } else {
        setError(err?.message || 'We could not restore the workspace. Try again.');
      }
      setBusy('');
    }
  };

  const handleExport = async () => {
    if (busy) return;
    setBusy('export');
    setError('');
    setExportNote('');
    try {
      const res = await api.tenant.createExport();
      if (res?.jobId) {
        await api.tenant.downloadExportArchive(res.jobId);
        setExportNote('Your data download has started.');
      } else {
        setExportNote(res?.message || 'Your export is being prepared.');
      }
    } catch (err) {
      setError(err?.message || 'We could not prepare your data. Try again.');
    } finally {
      setBusy('');
    }
  };

  const handleLeave = async () => {
    if (busy) return;
    setBusy('leave');
    try {
      await logout();
    } finally {
      window.location.href = '/';
    }
  };

  return (
    <main
      className="min-h-screen bg-canvas text-ink font-sans antialiased px-4 py-10 sm:py-16"
      data-testid="workspace-restore-screen"
    >
      <div className="mx-auto w-full max-w-xl min-w-0 space-y-4">
        <SolidCard>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="warning" dot>
              Scheduled for deletion
            </Badge>
          </div>
          <h1 className="mt-3 text-heading sm:text-display text-ink break-words">{workspaceName}</h1>
          <p className="mt-2 text-copy text-fg-body">
            {status?.deletedByYou ? 'You deleted this workspace. ' : 'This workspace was deleted by an admin. '}
            It will be permanently deleted on <strong className="font-semibold text-ink">{purgeDate}</strong>
            {status?.daysRemaining > 0 ? ` (${plural(status.daysRemaining, 'day', 'days')} left)` : ''}. Until
            then, its calls, numbers and campaigns are paused.
          </p>

          {loadError && (
            <div className="mt-4 rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg" role="alert">
              {loadError}{' '}
              <button type="button" className="font-semibold underline" onClick={load}>
                Try again
              </button>
            </div>
          )}

          {status && canRestore && (
            <>
              <h2 className="mt-6 text-title text-ink">Restoring brings back</h2>
              <ul className="mt-2 space-y-1.5 text-copy text-fg-body" data-testid="restore-preview">
                <li>{plural(preview.agents || 0, 'AI employee', 'AI employees')} with their scripts and settings</li>
                <li>
                  {plural(preview.phoneNumbers || 0, 'phone number', 'phone numbers')}, answering and calling again
                </li>
                <li>{walletLine(preview)}, untouched</li>
                {preview.integrations > 0 && <li>{plural(preview.integrations, 'connected app', 'connected apps')}</li>}
                <li>Call history, leads and recordings</li>
              </ul>
              {preview.campaignsPaused > 0 && (
                <p className="mt-3 rounded-control border border-info-line bg-info-soft px-3 py-2 text-ui text-info-fg">
                  {plural(preview.campaignsPaused, 'campaign stays', 'campaigns stay')} paused after the restore, so no
                  one is called before you check it. Resume from Campaigns when you are ready.
                </p>
              )}

              <form className="mt-6 space-y-3" onSubmit={handleRestore}>
                {needsPassword && hasPassword && (
                  <label className="block">
                    <span className="text-ui font-medium text-ink">Confirm your password</span>
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="mt-1 w-full rounded-control border border-line bg-surface px-3 py-2 text-base sm:text-ui text-ink focus:outline-none focus:ring-2 focus:ring-accent"
                      data-testid="restore-password"
                    />
                    <span className="mt-1 block text-meta text-fg-muted">
                      You signed in a while ago, so we need to check it is you.
                    </span>
                  </label>
                )}
                {needsPassword && !hasPassword && (
                  <p className="text-ui text-fg-body">
                    You signed in a while ago. Sign out, sign in again with Google, and restore within 15 minutes.
                  </p>
                )}
                {error && (
                  <p className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg" role="alert">
                    {error}
                  </p>
                )}
                {exportNote && <p className="text-ui text-success-fg">{exportNote}</p>}
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                  <TactileButton
                    type="submit"
                    variant="brand"
                    icon={RotateCcw}
                    loading={busy === 'restore'}
                    disabled={Boolean(busy) || (needsPassword && (!hasPassword || !password))}
                    data-testid="restore-workspace"
                  >
                    Restore workspace
                  </TactileButton>
                  <TactileButton
                    variant="secondary"
                    icon={Download}
                    loading={busy === 'export'}
                    disabled={Boolean(busy)}
                    onClick={handleExport}
                  >
                    Download my data
                  </TactileButton>
                  <TactileButton
                    variant="ghost"
                    icon={LogOut}
                    loading={busy === 'leave'}
                    disabled={Boolean(busy)}
                    onClick={handleLeave}
                    data-testid="continue-deletion"
                  >
                    Keep deletion and sign out
                  </TactileButton>
                </div>
              </form>
            </>
          )}

          {status && !canRestore && (
            <div className="mt-6 space-y-3" data-testid="restore-blocked">
              <p className="text-copy text-fg-body">
                {blocked === 'grace_expired'
                  ? 'The grace period has ended, so this workspace can no longer be restored.'
                  : blocked === 'impersonation'
                    ? 'A support session cannot restore a workspace. The owner needs to sign in and restore it.'
                    : 'Only the workspace owner can restore it. Ask them to sign in before this date if you still need it.'}
              </p>
              <TactileButton variant="secondary" icon={LogOut} loading={busy === 'leave'} onClick={handleLeave}>
                Sign out
              </TactileButton>
            </div>
          )}

          {!status && !loadError && <p className="mt-6 text-ui text-fg-muted">Loading workspace details…</p>}
        </SolidCard>

        <p className="flex items-start gap-2 px-1 text-meta text-fg-muted">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Only the owner can restore, and only after confirming it is them. Every restore is recorded.
        </p>
        <p className="flex items-start gap-2 px-1 text-meta text-fg-muted">
          <CalendarClock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          After {purgeDate}, the workspace and its data are deleted for good and cannot be recovered.
        </p>
      </div>
    </main>
  );
}
