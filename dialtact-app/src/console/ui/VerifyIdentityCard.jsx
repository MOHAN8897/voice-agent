import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  // One status poll at a time, always cleared on unmount.
  const pollRef = useRef(null);
  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

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
      stopPolling();
      let tries = 0;
      const poll = window.setInterval(async () => {
        tries += 1;
        if (tries >= 40) stopPolling();
        try {
          const next = await api.kyc.getStatus();
          if (pollRef.current !== poll && tries < 40) return;
          setStatus(next);
          if (next?.approved) {
            stopPolling();
            showToast('Identity verified', 'success');
            onApproved?.(next);
          }
        } catch {
          /* keep polling */
        }
      }, 3000);
      pollRef.current = poll;
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
          className="rounded-card border border-line bg-canvas p-6 sm:p-8 space-y-6 animate-pulse"
          data-testid="kyc-status-loading"
          aria-busy="true"
        >
          <div className="flex flex-col items-center text-center space-y-3">
            <div className="w-14 h-14 rounded-card bg-line" />
            <div className="space-y-2 max-w-sm w-full flex flex-col items-center">
              <div className="h-5 w-48 bg-line rounded-control" />
              <div className="h-3 w-64 bg-line/70 rounded" />
              <div className="h-3 w-48 bg-line/60 rounded" />
            </div>
          </div>
          <div className="h-10 w-full rounded-control bg-line max-w-xs mx-auto" />
        </div>
      );
    }
    if (compact) {
      return (
        <div
          className="rounded-control border border-line bg-canvas p-3 flex items-center justify-between gap-3 animate-pulse"
          data-testid="kyc-status-loading"
          aria-busy="true"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-control bg-line" />
            <div className="space-y-1">
              <div className="h-3 w-28 bg-line rounded" />
              <div className="h-2 w-20 bg-line/60 rounded" />
            </div>
          </div>
          <div className="h-6 w-16 bg-line rounded-control" />
        </div>
      );
    }
    return (
      <div
        className="rounded-card border border-line bg-canvas p-4 space-y-3 animate-pulse"
        data-testid="kyc-status-loading"
        aria-busy="true"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-control bg-line" />
            <div className="space-y-1">
              <div className="h-3.5 w-32 bg-line rounded" />
              <div className="h-2.5 w-24 bg-line/60 rounded" />
            </div>
          </div>
          <div className="h-6 w-20 bg-line rounded-control" />
        </div>
        <div className="h-8 w-28 bg-line rounded-control" />
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
        className="rounded-card border border-line bg-gradient-to-b from-surface to-canvas p-6 sm:p-8 space-y-6"
        data-testid="kyc-verify-card"
        data-variant="gate"
      >
        <div className="flex flex-col items-center text-center space-y-3">
          <div className="w-14 h-14 rounded-card bg-accent-soft border border-line flex items-center justify-center">
            <Shield className="w-7 h-7 text-accent-fg" strokeWidth={1.75} />
          </div>
          <div className="space-y-1.5 max-w-sm">
            <h3 className="text-title text-ink">
              Verify your identity first
            </h3>
            <p className="text-ui text-fg-body">
              Phone numbers and live calls require a quick ID check. It takes about a minute:
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
              className={`rounded-control border px-2 py-2.5 ${
                i === 0
                  ? 'border-accent/30 bg-accent-soft'
                  : 'border-line bg-surface opacity-60'
              }`}
            >
              <span
                className={`inline-flex w-5 h-5 items-center justify-center rounded-full text-meta font-bold mb-1 ${
                  i === 0 ? 'bg-accent text-white' : 'bg-line text-fg-body'
                }`}
              >
                {step.n}
              </span>
              <p className="text-meta font-medium text-ink">{step.t}</p>
            </li>
          ))}
        </ol>

        {!configured && (
          <p className="text-meta text-center text-warning-fg" data-testid="kyc-not-configured">
            Identity verification is not available yet. Contact support to continue.
          </p>
        )}
        {error && (
          <p className="text-meta text-center text-danger-fg" role="alert" data-testid="kyc-error">
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
            className="w-full min-h-[36px] text-ui font-semibold text-accent-fg hover:underline py-1"
            data-testid="kyc-refresh-status"
          >
            I have finished. Refresh status
          </button>
          <p className="text-meta text-center text-fg-muted">Status: {label}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-card border ${
        approved ? 'border-success-line bg-success-soft' : 'border-line bg-canvas'
      } ${compact ? 'p-3' : 'p-4'} space-y-2`}
      data-testid="kyc-verify-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          {approved ? (
            <BadgeCheck className="w-4 h-4 text-success-fg shrink-0 mt-0.5" />
          ) : (
            <Shield className="w-4 h-4 text-accent-fg shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <p className="text-copy font-semibold text-ink">
              {approved ? 'Identity verified' : 'Verify your identity'}
            </p>
            <p className="text-ui text-fg-body mt-0.5">
              {approved
                ? 'You can buy phone numbers and place live calls.'
                : status?.required ? 'Required before you can buy numbers or place live calls.' : 'Optional. This is separate from phone service verification.'}
            </p>
            <p className="text-meta text-fg-muted mt-1 flex items-center gap-1">
              {approved ? <Check className="w-3 h-3 text-success-fg" /> : null}
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
        <p className="text-meta text-warning-fg" data-testid="kyc-not-configured">
          Identity verification is not available yet. Contact support to continue.
        </p>
      )}
      {error && (
        <p className="text-meta text-danger-fg" role="alert" data-testid="kyc-error">
          {error}
        </p>
      )}
      {!approved && (
        <button
          type="button"
          onClick={refresh}
          className="text-meta font-semibold text-accent-fg hover:underline"
          data-testid="kyc-refresh-status"
        >
          I finished verification — refresh status
        </button>
      )}
    </div>
  );
}
