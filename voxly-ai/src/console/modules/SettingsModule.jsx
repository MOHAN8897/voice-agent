import React, { useState } from 'react';
import { Eye, EyeOff, KeyRound, Shield, Users, Wallet } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { useAuth } from '../../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { VerifyIdentityCard } from '../ui/VerifyIdentityCard';
import { api } from '../../services/api';
import { analytics } from '../../services/analytics';

const MIN_LENGTH = 8;

function PasswordField({ id, label, value, onChange, autoComplete, testId, show, onToggle }) {
  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-semibold text-[#0F0E17] mb-1">
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
          className="w-full text-base sm:text-xs min-h-[42px] sm:min-h-[38px] px-3.5 py-2.5 pr-9 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#6344E7] text-[#0F0E17]"
        />
        <button
          type="button"
          onClick={onToggle}
          tabIndex={-1}
          aria-label={show ? 'Hide password' : 'Show password'}
          className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center text-[#635F70] hover:text-[#0F0E17]"
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
    <SolidCard className="space-y-3">
      <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
        <KeyRound className="w-3.5 h-3.5 text-[#6344E7]" />
        Password
      </h3>
      <p className="text-[11px] text-[#524E5E] leading-relaxed">
        Changing your password signs out every other device and browser. This session stays signed in.
      </p>

      {error && (
        <p
          data-testid="change-password-error"
          className="text-[11px] font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2"
        >
          {error}
        </p>
      )}
      {notice && (
        <p
          data-testid="change-password-notice"
          className="text-[11px] font-medium text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-2"
        >
          {notice}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-3" data-testid="change-password-form">
        <PasswordField
          id="voxly-current-password"
          label="Current password"
          value={currentPassword}
          onChange={setCurrentPassword}
          autoComplete="current-password"
          testId="change-password-current"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <PasswordField
          id="voxly-new-password"
          label="New password"
          value={newPassword}
          onChange={setNewPassword}
          autoComplete="new-password"
          testId="change-password-new"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <PasswordField
          id="voxly-confirm-password"
          label="Confirm new password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          autoComplete="new-password"
          testId="change-password-confirm"
          show={show}
          onToggle={() => setShow((v) => !v)}
        />
        <button
          type="submit"
          disabled={busy}
          data-testid="change-password-submit"
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 min-h-[44px] sm:min-h-[38px] rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all disabled:opacity-60"
        >
          {busy ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </SolidCard>
  );
}

export function SettingsModule() {
  const { user, isPlatformAdmin, isDevTester, sessionPolicy } = useAuth();
  const { wallet } = useWorkspace();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Workspace Settings</h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Account and organization settings are managed through your signed-in session. Admin access is
          decided by the API on every request.
        </p>
      </div>

      <SolidCard className="space-y-3">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-[#6344E7]" />
          Identity verification
        </h3>
        <p className="text-[11px] text-[#524E5E] leading-relaxed">
          Complete KYC once. Buying phone numbers and placing live phone calls require an approved
          identity check.
        </p>
        <VerifyIdentityCard />
      </SolidCard>

      <SecurityPasswordCard />

      <SolidCard className="space-y-3">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-[#6344E7]" />
          Session security
        </h3>
        <p className="text-[11px] text-[#524E5E] leading-relaxed">
          You are signed out automatically after{' '}
          <strong data-testid="session-idle-minutes">
            {sessionPolicy?.idleTimeoutMinutes ?? 30} minutes
          </strong>{' '}
          of inactivity, with a 2-minute countdown so you are never logged out by surprise. A single
          sign-in cannot last longer than {sessionPolicy?.absoluteMaxHours ?? 24} hours.
        </p>
      </SolidCard>

      <SolidCard className="space-y-3">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Users className="w-3.5 h-3.5 text-[#6344E7]" />
          Signed-in user
        </h3>
        <p className="text-sm text-[#0F0E17] font-medium">{user?.name || user?.email || '—'}</p>
        <p className="text-xs text-[#524E5E]">{user?.email}</p>
        {user?.tenantName && (
          <p className="text-xs text-[#524E5E]">Organization: {user.tenantName}</p>
        )}
        <p className="text-xs text-[#524E5E]">
          Role: {user?.role || 'member'}
          {isPlatformAdmin ? ' · platform admin' : ''}
          {isDevTester && !isPlatformAdmin ? ' · dev tester' : ''}
        </p>
      </SolidCard>

      <SolidCard className="space-y-2">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Wallet className="w-3.5 h-3.5 text-[#6344E7]" />
          Credits
        </h3>
        <p className="text-sm font-mono font-semibold text-[#0F0E17]">
          {Number(wallet?.remainingMinutes || 0).toLocaleString()} min
        </p>
        <p className="text-xs text-[#524E5E]">
          {`$${Number(wallet?.balanceUsd || 0).toFixed(2)} workspace wallet`}
          {wallet?.myUsageUsd != null ? ` · your usage $${Number(wallet.myUsageUsd).toFixed(2)}` : ''}
        </p>
      </SolidCard>

      <SolidCard className="space-y-2">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-[#15803D]" />
          API access
        </h3>
        <p className="text-xs text-[#524E5E] leading-relaxed">
          Programmatic API keys and team invites are not enabled in this console build yet. Use the
          subscriber JWT from sign-in for authenticated API calls during development, or contact support
          for service accounts.
        </p>
      </SolidCard>
    </div>
  );
}

export default SettingsModule;