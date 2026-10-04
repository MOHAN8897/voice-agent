import React, { useCallback, useEffect, useState } from 'react';
import { BadgeCheck, Check, Loader2, Shield, ExternalLink } from 'lucide-react';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import { TactileButton } from '../ui/TactileButton';

/**
 * Identity verification for Settings and the buy-number gate.
 * Never treats the browser return as approval — only Approved via webhook.
 *
 * variant="gate" — full-step UI when buying a number before KYC is done.
 * compact — small banner for Settings.
 */
export function VerifyIdentityCard({ compact = false, variant = 'default', onApproved } = {}) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.kyc.getStatus();
      setStatus(next);
      if (next?.approved) onApproved?.(next);
    } catch (e) {
      setError(e.message || 'Could not load verification status');
    } finally {
      setLoading(false);
    }
  }, [onApproved]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onFocus = () => {
      refresh();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refresh]);

  const startVerification = async () => {
    setStarting(true);
    setError(null);
    try {
      if (status?.approved) {
        onApproved?.(status);
        showToast('Identity already verified', 'success', 3000);
        return;
      }
      const session = await api.kyc.createSession();
      if (session?.approved) {
        const next = { ...session, approved: true };
        setStatus(next);
        onApproved?.(next);
        showToast('Identity already verified', 'success', 3000);
        return;
      }
      const url = session?.url;
      if (!url) {
        throw new Error('Verification could not start. Please try again.');
      }
      showToast('Opening identity verification…', 'info', 4000);
      window.open(url, '_blank', 'noopener,noreferrer');
      let tries = 0;
      const poll = window.setInterval(async () => {
        tries += 1;
        try {
          const next = await api.kyc.getStatus();
          setStatus(next);
          if (next?.approved) {
            window.clearInterval(poll);
            showToast('Identity verified', 'success');
            onApproved?.(next);
          }
        } catch {
          /* keep polling */
        }
        if (tries >= 40) window.clearInterval(poll);
      }, 3000);
    } catch (e) {
      const msg =
        e.code === 'kyc_not_configured'
          ? 'Identity verification is not available yet. Contact support to continue.'
          : e.message || 'Could not start identity verification';
      setError(msg);
      showToast(msg, 'error', 5000);
    } finally {
      setStarting(false);
    }
  };

  // chisel: variant-specific layout-stable skeletons while Didit/KYC state resolves
  if (loading) {
    if (variant === 'gate') {
      return (
        <div
          className="rounded-2xl border border-[#E4E2EB] bg-[#FAF9FD] p-6 sm:p-8 space-y-6 animate-pulse"
          data-testid="kyc-status-loading"
          aria-busy="true"
        >
          <div className="flex flex-col items-center text-center space-y-3">
            <div className="w-14 h-14 rounded-2xl bg-[#E4E2EB]" />
            <div className="space-y-2 max-w-sm w-full flex flex-col items-center">
              <div className="h-5 w-48 bg-[#E4E2EB] rounded-md" />
              <div className="h-3 w-64 bg-[#E4E2EB]/70 rounded" />
              <div className="h-3 w-48 bg-[#E4E2EB]/60 rounded" />
            </div>
          </div>
          <div className="h-10 w-full rounded-xl bg-[#E4E2EB] max-w-xs mx-auto" />
        </div>
      );
    }
    if (compact) {
      return (
        <div
          className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-3 flex items-center justify-between gap-3 animate-pulse"
          data-testid="kyc-status-loading"
          aria-busy="true"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-[#E4E2EB]" />
            <div className="space-y-1">
              <div className="h-3 w-28 bg-[#E4E2EB] rounded" />
              <div className="h-2 w-20 bg-[#E4E2EB]/60 rounded" />
            </div>
          </div>
          <div className="h-6 w-16 bg-[#E4E2EB] rounded-md" />
        </div>
      );
    }
    return (
      <div
        className="rounded-2xl border border-[#E4E2EB] bg-[#FAF9FD] p-4 space-y-3 animate-pulse"
        data-testid="kyc-status-loading"
        aria-busy="true"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#E4E2EB]" />
            <div className="space-y-1">
              <div className="h-3.5 w-32 bg-[#E4E2EB] rounded" />
              <div className="h-2.5 w-24 bg-[#E4E2EB]/60 rounded" />
            </div>
          </div>
          <div className="h-6 w-20 bg-[#E4E2EB] rounded-md" />
        </div>
        <div className="h-8 w-28 bg-[#E4E2EB] rounded-lg" />
      </div>
    );
  }

  const approved = Boolean(status?.approved);
  const configured = status?.configured !== false;
  const label = approved
    ? 'Approved'
    : status?.status && status.status !== 'Not Started'
      ? status.status
      : 'Not started';

  if (variant === 'gate' && !approved) {
    return (
      <div
        className="rounded-2xl border border-[#E4E2EB] bg-gradient-to-b from-white to-[#FAF9FD] p-6 sm:p-8 space-y-6"
        data-testid="kyc-verify-card"
        data-variant="gate"
      >
        <div className="flex flex-col items-center text-center space-y-3">
          <div className="w-14 h-14 rounded-2xl bg-[#F3F0FF] border border-[#E4E2EB] flex items-center justify-center">
            <Shield className="w-7 h-7 text-[#6344E7]" strokeWidth={1.75} />
          </div>
          <div className="space-y-1.5 max-w-sm">
            <h3 className="text-base font-bold text-[#0F0E17] tracking-tight">
              Verify your identity first
            </h3>
            <p className="text-xs text-[#524E5E] leading-relaxed">
              Phone numbers and live calls require a quick ID check. Takes about a minute —
              government ID and a selfie. Your documents stay with the verification partner.
            </p>
          </div>
        </div>

        <ol className="grid grid-cols-3 gap-2 text-center">
          {[
            { n: '1', t: 'Verify ID' },
            { n: '2', t: 'Pick a number' },
            { n: '3', t: 'Activate' },
          ].map((step, i) => (
            <li
              key={step.n}
              className={`rounded-xl border px-2 py-2.5 ${
                i === 0
                  ? 'border-[#6344E7]/30 bg-[#F3F0FF]'
                  : 'border-[#E4E2EB] bg-white opacity-60'
              }`}
            >
              <span
                className={`inline-flex w-5 h-5 items-center justify-center rounded-full text-[10px] font-bold mb-1 ${
                  i === 0 ? 'bg-[#6344E7] text-white' : 'bg-[#E4E2EB] text-[#524E5E]'
                }`}
              >
                {step.n}
              </span>
              <p className="text-[10px] font-semibold text-[#0F0E17]">{step.t}</p>
            </li>
          ))}
        </ol>

        {!configured && (
          <p className="text-[11px] text-center text-[#B45309]" data-testid="kyc-not-configured">
            Identity verification is not available yet. Contact support to continue.
          </p>
        )}
        {error && (
          <p className="text-[11px] text-center text-red-800" role="alert" data-testid="kyc-error">
            {error}
          </p>
        )}

        <div className="space-y-2">
          <TactileButton
            size="md"
            variant="brand"
            disabled={starting || !configured}
            loading={starting}
            onClick={startVerification}
            data-testid="kyc-start-verification"
            icon={ExternalLink}
            className="w-full justify-center"
          >
            {starting ? 'Opening…' : 'Start verification'}
          </TactileButton>
          <button
            type="button"
            onClick={refresh}
            className="w-full text-[11px] font-semibold text-[#6344E7] hover:underline py-1"
            data-testid="kyc-refresh-status"
          >
            I finished — refresh status
          </button>
          <p className="text-[10px] text-center text-[#8C879A]">Status: {label}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border ${
        approved ? 'border-emerald-200 bg-emerald-50' : 'border-[#E4E2EB] bg-[#FAF9FD]'
      } ${compact ? 'p-3' : 'p-4'} space-y-2`}
      data-testid="kyc-verify-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {approved ? (
            <BadgeCheck className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
          ) : (
            <Shield className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <p className="text-xs font-bold text-[#0F0E17]">
              {approved ? 'Identity verified' : 'Verify your identity'}
            </p>
            <p className="text-[11px] text-[#524E5E] leading-relaxed mt-0.5">
              {approved
                ? 'You can buy phone numbers and place live calls.'
                : 'Required before buying a phone number or placing live calls. ID check takes about a minute.'}
            </p>
            <p className="text-[10px] text-[#8C879A] mt-1 flex items-center gap-1">
              {approved ? <Check className="w-3 h-3 text-emerald-600" /> : null}
              Status: {label}
            </p>
          </div>
        </div>
        {!approved && (
          <TactileButton
            size="xs"
            variant="primary"
            disabled={starting || !configured}
            loading={starting}
            onClick={startVerification}
            data-testid="kyc-start-verification"
            icon={ExternalLink}
          >
            {starting ? 'Starting…' : 'Start verification'}
          </TactileButton>
        )}
      </div>
      {!configured && !approved && (
        <p className="text-[11px] text-[#B45309]" data-testid="kyc-not-configured">
          Identity verification is not available yet. Contact support to continue.
        </p>
      )}
      {error && (
        <p className="text-[11px] text-red-800" role="alert" data-testid="kyc-error">
          {error}
        </p>
      )}
      {!approved && (
        <button
          type="button"
          onClick={refresh}
          className="text-[11px] font-semibold text-[#6344E7] hover:underline"
          data-testid="kyc-refresh-status"
        >
          I finished verification — refresh status
        </button>
      )}
    </div>
  );
}
