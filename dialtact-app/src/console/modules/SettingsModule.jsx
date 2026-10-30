import React, { useState } from 'react';
import { AlertTriangle, Eye, EyeOff, KeyRound, Shield, Users, Wallet } from 'lucide-react';
import { SolidCard, Section } from '../ui/SolidCard';
import { PageHeader } from '../ui/PageHeader';
import { TactileButton } from '../ui/TactileButton';
import { formatInr, formatUsd, walletAmounts } from '../../lib/money';
import { humanizeToken } from '../../lib/internalLabels';
import { DeleteWorkspaceModal } from '../ui/DeleteWorkspaceModal';
import { useAuth } from '../../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { VerifyIdentityCard } from '../ui/VerifyIdentityCard';
import { VoiceServiceKycCard } from '../ui/VoiceServiceKycCard';
import { api } from '../../services/api';
import { analytics } from '../../services/analytics';

const MIN_LENGTH = 8;

function formatIdleWindow(minutes) {
  const value = Number(minutes) || 0;
  if (value >= 60 && value % 60 === 0) {
    const hours = value / 60;
    return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }
  return `${value} minutes`;
}

function PasswordField({ id, label, value, onChange, autoComplete, testId, show, onToggle }) {
  return (
    <div>
      <label htmlFor={id} className="block text-ui font-medium text-ink mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          minLength={MIN_LENGTH}
          required
          data-testid={testId}
          className="w-full text-base sm:text-ui min-h-[44px] sm:min-h-[38px] px-3.5 py-2.5 pr-10 rounded-control bg-surface border border-line focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink"
        />
        <button
          type="button"
          onClick={onToggle}
          tabIndex={-1}
          aria-label={show ? 'Hide password' : 'Show password'}
          className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center text-fg-muted hover:text-ink"
        >
          {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}

/**
 * Change password.
 *
 * `POST /api/auth/change-password` existed on the backend with no way to reach it, so
 * the only way to change a password was to sign out and go through the reset email.
 * Changing it here keeps the user signed in: the server revokes every other session
 * for the account (a password change must lock out anyone holding a stolen cookie) and
 * hands this browser a fresh one.
 */
function SecurityPasswordCard() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const reset = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError('');
    setNotice('');

    if (newPassword.length < MIN_LENGTH) {
      setError(`New password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('The two new passwords do not match.');
      return;
    }
    if (newPassword === currentPassword) {
      setError('Choose a password different from the current one.');
      return;
    }

    setBusy(true);
    try {
      await api.auth.changePassword(currentPassword, newPassword);
      analytics.track('auth_password_changed');
      setNotice('Password updated. Other sessions were signed out; you are still signed in here.');
      reset();
    } catch (err) {
      setError(err?.message || 'Could not change the password.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section
      title={<span className="flex items-center gap-2"><KeyRound className="w-4 h-4 text-fg-subtle" aria-hidden="true" />Password</span>}
      description="Changing your password signs out every other device and browser. This session stays signed in."
    >
      <div className="space-y-3">

      {error && (
        <p
          data-testid="change-password-error"
          className="text-ui font-medium text-danger-fg bg-danger-soft border border-danger-line rounded-control px-3 py-2"
        >
          {error}
        </p>
      )}
      {notice && (
        <p
          data-testid="change-password-notice"
          className="text-ui font-medium text-success-fg bg-success-soft border border-success-line rounded-control px-3 py-2"
        >
          {notice}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-3 max-w-md" data-testid="change-password-form">
        <PasswordField
          id="dialtact-current-password"
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          autoComplete="current-password"
          testId="change-password-current"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <PasswordField
          id="dialtact-new-password"
          label="New password"
          value={newPassword}
          onChange={setNewPassword}
          autoComplete="new-password"
          testId="change-password-new"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <PasswordField
          id="dialtact-confirm-password"
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          autoComplete="new-password"
          testId="change-password-confirm"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <TactileButton
          type="submit"
          variant="primary"
          size="md"
          disabled={busy}
          data-testid="change-password-submit"
          className="w-full sm:w-auto"
        >
          {busy ? 'Updating…' : 'Update password'}
        </TactileButton>
      </form>
      </div>
    </Section>
  );
}

export function SettingsModule() {
  const { user, isPlatformAdmin, isDevTester, sessionPolicy } = useAuth();
  const { wallet } = useWorkspace();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Your account, sign-in security, verification and workspace."
      />

      <Section
        title={<span className="flex items-center gap-2"><Shield className="w-4 h-4 text-fg-subtle" aria-hidden="true" />Phone service verification</span>}
        description="Needed before you can buy numbers or place live phone calls."
      >
        <div className="space-y-3">
          <VoiceServiceKycCard />
          <details className="group">
            <summary className="cursor-pointer min-h-[36px] flex items-center text-ui font-medium text-fg-body hover:text-ink">Identity verification (only when asked)</summary>
            <div className="mt-3"><VerifyIdentityCard /></div>
          </details>
        </div>
      </Section>

      <SecurityPasswordCard />

      <Section
        title={<span className="flex items-center gap-2"><Shield className="w-4 h-4 text-fg-subtle" aria-hidden="true" />Sign-in security</span>}
      >
        <div className="space-y-2">
        {user?.rememberMe ? (
          <p className="text-ui text-fg-body" data-testid="session-remember-status">
            This device is set to keep you signed in. You will still be signed out automatically after
            an extended period of inactivity, and every session ends at its maximum age. Sign out
            before leaving a shared computer.
          </p>
        ) : (
          <>
            <p className="text-ui text-fg-body">
              You are signed out automatically after{' '}
              <strong className="font-semibold text-ink" data-testid="session-idle-minutes">
                {formatIdleWindow(sessionPolicy?.idleTimeoutMinutes ?? 360)}
              </strong>{' '}
              of inactivity, with a 2-minute countdown so you are never logged out by surprise. A single
              sign-in cannot last longer than {sessionPolicy?.absoluteMaxHours ?? 24} hours.
            </p>
            <p className="text-ui text-fg-body">
              Tick “Keep me signed in” on the sign-in form to stay signed in on this device. Leave it
              off on shared computers.
            </p>
          </>
        )}
        </div>
      </Section>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Section
          title={<span className="flex items-center gap-2"><Users className="w-4 h-4 text-fg-subtle" aria-hidden="true" />Signed in as</span>}
          className="min-w-0"
        >
          <div className="space-y-1">
            <p className="text-copy text-ink font-medium break-words">{user?.name || user?.email || '—'}</p>
            <p className="text-ui text-fg-body break-all">{user?.email}</p>
            {user?.tenantName && (
              <p className="text-ui text-fg-body">Organisation: {user.tenantName}</p>
            )}
            <p className="text-ui text-fg-body">
              Role: {humanizeToken(user?.role || 'member')}
              {isPlatformAdmin ? ' · platform admin' : ''}
              {isDevTester && !isPlatformAdmin ? ' · test account' : ''}
            </p>
          </div>
        </Section>

        <Section
          title={<span className="flex items-center gap-2"><Wallet className="w-4 h-4 text-fg-subtle" aria-hidden="true" />Wallet</span>}
          className="min-w-0"
        >
          <div className="space-y-1">
            <p className="text-heading font-mono tabular-nums text-ink" data-testid="settings-wallet-balance">
              {walletAmounts(wallet).primary}
            </p>
            <p className="text-ui text-fg-body">
              <span className="font-mono tabular-nums">{Number(wallet?.remainingMinutes || 0).toLocaleString('en-IN')} min</span> of talk time
              <span className="text-fg-muted"> · <span className="font-mono tabular-nums">{walletAmounts(wallet).secondary}</span></span>
            </p>
            {wallet?.myUsageUsd != null ? (
              <p className="text-meta text-fg-muted">
                Your usage: <span className="font-mono tabular-nums">{formatInr(Number(wallet.myUsageUsd) * (Number(wallet?.fxRateInr) || 95.64))}</span>{' '}
                (<span className="font-mono tabular-nums">{formatUsd(wallet.myUsageUsd)}</span>)
              </p>
            ) : null}
          </div>
        </Section>
      </div>

      <Section
        title={<span className="flex items-center gap-2"><Shield className="w-4 h-4 text-fg-subtle" aria-hidden="true" />API access</span>}
      >
        <p className="text-ui text-fg-body">
          API keys and team invites are not available in the console yet. Contact support if another
          system needs to connect to your workspace.
        </p>
      </Section>

      {(user?.role === 'owner' || user?.role === 'customer_admin' || user?.role === 'platform_admin' || user?.isPlatformAdmin) && (
        <SolidCard className="space-y-3 !border-danger-line" data-testid="danger-zone-card">
          <h2 className="text-title text-danger-fg flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-danger-fg" aria-hidden="true" />
            Delete workspace
          </h2>
          <p className="text-ui text-fg-body">
            Permanently delete this workspace, including all agents, phone numbers, integrations and call records.
            You have 14 days to change your mind before everything is erased.
          </p>
          <div className="pt-1">
            <TactileButton
              variant="danger"
              size="md"
              icon={AlertTriangle}
              onClick={() => setIsDeleteModalOpen(true)}
              data-testid="danger-zone-delete-button"
            >
              Delete workspace
            </TactileButton>
          </div>
        </SolidCard>
      )}

      <DeleteWorkspaceModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        tenantName={user?.tenantName || ''}
      />
    </div>
  );
}

export default SettingsModule;
