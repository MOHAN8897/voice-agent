import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BadgeCheck, ExternalLink, Loader2, Shield, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { TactileButton } from './TactileButton';

const BUSINESS_TYPES = [
  ['individual', 'Individual'],
  ['proprietorship', 'Sole proprietorship'],
  ['private_limited', 'Private limited company'],
  ['llp', 'Limited liability partnership'],
  ['partnership', 'Partnership'],
  ['public_limited', 'Public limited company'],
  ['trust', 'Trust'],
  ['society', 'Society'],
  ['huf', 'Hindu undivided family'],
  ['government', 'Government'],
];

function statusLabel(status) {
  if (status === 'verified') return 'Verified';
  if (status === 'pending') return 'In review';
  if (status === 'failed') return 'Needs more information';
  if (status === 'not_started') return 'Not started';
  if (status === 'creating') return 'Setting up';
  return 'Needs support';
}

const PENDING_KYC_KEY = 'dialtact_voice_kyc_pending';

/** Survives the return tab / reload so the first check after returning asks the carrier. */
function readPendingKyc() {
  try {
    return window.localStorage.getItem(PENDING_KYC_KEY) === '1';
  } catch {
    return false;
  }
}

function writePendingKyc(pending) {
  try {
    if (pending) window.localStorage.setItem(PENDING_KYC_KEY, '1');
    else window.localStorage.removeItem(PENDING_KYC_KEY);
  } catch {
    /* storage unavailable: fall back to non-forced refreshes */
  }
}

export function VoiceServiceKycCard({ onApproved }) {
  const onApprovedRef = useRef(onApproved);
  const requestId = useRef(0);
  const [status, setStatus] = useState(null);
  const [businessType, setBusinessType] = useState('');
  const [legalName, setLegalName] = useState('');
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    onApprovedRef.current = onApproved;
  }, [onApproved]);

  // Approved is terminal: once seen, background refreshes stop.
  const approvedRef = useRef(false);
  // The carrier is asked again (force) only after the user opened the KYC tab.
  const awaitingReturnRef = useRef(readPendingKyc());

  const refresh = useCallback(async (force = false) => {
    const current = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const next = await api.kyc.getVoiceStatus({ refresh: force === true });
      if (current !== requestId.current) return;
      setStatus(next);
      if (next?.businessType) setBusinessType(next.businessType);
      if (next?.legalName) setLegalName(next.legalName);
      if (next?.approved) {
        approvedRef.current = true;
        awaitingReturnRef.current = false;
        writePendingKyc(false);
        onApprovedRef.current?.(next);
      }
    } catch (e) {
      if (current !== requestId.current) return;
      setError(e.message || 'Could not load phone service verification status.');
    } finally {
      if (current === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh(awaitingReturnRef.current);
    const onResume = () => {
      if (approvedRef.current) return;
      refresh(awaitingReturnRef.current);
    };
    const timer = window.setInterval(() => {
      if (!approvedRef.current && document.visibilityState === 'visible') refresh();
    }, 30000);
    window.addEventListener('focus', onResume);
    window.addEventListener('pageshow', onResume);
    return () => {
      requestId.current += 1;
      window.clearInterval(timer);
      window.removeEventListener('focus', onResume);
      window.removeEventListener('pageshow', onResume);
    };
  }, [refresh]);

  const [openedUrl, setOpenedUrl] = useState('');

  const start = async () => {
    setStarting(true);
    setError('');
    // Open a blank tab synchronously on click to prevent popup blockers from intercepting it
    let newTab = null;
    try {
      newTab = window.open('about:blank', '_blank');
    } catch {
      newTab = null;
    }

    try {
      const result = await api.kyc.startVoiceSession({
        legal_name: legalName.trim(),
        business_type: businessType,
        return_url: window.location.href,
      });
      setStatus(result);
      if (result?.approved) {
        if (newTab && !newTab.closed) newTab.close();
        onApprovedRef.current?.(result);
        return;
      }
      if (!result?.sessionUrl) {
        if (newTab && !newTab.closed) newTab.close();
        throw new Error('Verification could not start. Please try again.');
      }
      setOpenedUrl(result.sessionUrl);
      awaitingReturnRef.current = true;
      writePendingKyc(true);
      if (newTab && !newTab.closed) {
        newTab.location.href = result.sessionUrl;
      } else {
        window.open(result.sessionUrl, '_blank', 'noopener,noreferrer');
      }
    } catch (e) {
      if (newTab && !newTab.closed) newTab.close();
      setError(e.message || 'Could not start phone service verification.');
    } finally {
      setStarting(false);
    }
  };

  if (status?.required === false) return null;

  if (loading && !status) {
    return (
      <div className="rounded-card border border-line bg-canvas p-6 space-y-4" aria-busy="true">
        <div className="flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-accent-fg" />
          <p className="text-copy text-fg-body">Checking phone service verification…</p>
        </div>
      </div>
    );
  }

  if (status?.approved) {
    return (
      <div className="rounded-card border border-success-line bg-success-soft p-6 text-center space-y-2" data-testid="voice-service-kyc-approved">
        <BadgeCheck className="w-9 h-9 text-success-fg mx-auto" />
        <h3 className="text-title text-success-fg">Phone service verified</h3>
        <p className="text-ui text-success-fg">You can continue with your number purchase and live calls.</p>
      </div>
    );
  }

  const canStart = status?.configured === true && !loading && !['creating', 'provisioning_unknown', 'credentials_lost'].includes(status?.status);
  const documents = ['individual', 'proprietorship', 'huf'].includes(businessType)
    ? 'Have your PAN and Aadhaar ready. Aadhaar verification uses DigiLocker with your consent.'
    : businessType ? 'Have the entity PAN and GST or CIN / registration details ready. The secure verification page will confirm the documents required for your entity.' : 'Choose the legal entity that will own the phone number.';

  return (
    <div className="rounded-card border border-line bg-gradient-to-b from-surface to-canvas p-5 sm:p-6 space-y-5" data-testid="voice-service-kyc-card">
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-control bg-accent-soft border border-line flex items-center justify-center shrink-0">
          <Shield className="w-5 h-5 text-accent-fg" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-title text-ink">Verify phone service</h3>
          <p className="mt-1 text-ui text-fg-body">
            Complete the secure identity check to activate phone numbers and live calls. The required documents depend on your legal entity type.
          </p>
          <p className="mt-2 text-ui text-fg-body">Use the legal name on your documents. Once this account is created, changing these legal details requires support.</p>
          <p className="mt-2 text-meta font-medium text-fg-muted">Status: <span className="text-ink">{statusLabel(status?.status)}</span></p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-ui font-medium text-fg-body">
          Legal entity type
          <select
            className="mt-1.5 block w-full rounded-control border border-line-strong bg-surface px-3 py-2.5 text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            value={businessType}
            disabled={starting || status?.identityLocked}
            onChange={(event) => setBusinessType(event.target.value)}
            data-testid="voice-service-business-type"
          >
            <option value="">Select entity type</option>
            {BUSINESS_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-ui font-medium text-fg-body">
          Legal name
          <input
            className="mt-1.5 block w-full rounded-control border border-line-strong bg-surface px-3 py-2.5 text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            value={legalName}
            disabled={starting || status?.identityLocked}
            onChange={(event) => setLegalName(event.target.value)}
            maxLength={255}
            autoComplete="organization"
            placeholder="Legal or registered business name"
            data-testid="voice-service-legal-name"
          />
        </label>
      </div>

      <p className="rounded-control bg-surface-subtle p-3 text-ui text-fg-body">{documents} A separate phone service account is created for your workspace. Complete verification on the secure hosted page, then return here to confirm your number purchase.</p>

      {status?.verifications && Object.keys(status.verifications).length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Verification document status">
          {Object.entries(status.verifications).map(([key, value]) => (
            <span key={key} className="rounded-pill border border-line bg-surface px-2.5 py-1 text-meta text-fg-body">
              {key.toUpperCase()}: {statusLabel(value)}
            </span>
          ))}
        </div>
      )}

      {status?.configured === false && (
        <p className="text-ui text-warning-fg" role="status">Phone service verification is not available yet. Contact support to continue.</p>
      )}
      {error && <p className="text-ui text-danger-fg" role="alert" data-testid="voice-service-kyc-error">{error}</p>}
      {openedUrl && (
        <div className="rounded-control border border-info-line bg-info-soft p-3.5 space-y-1.5 text-ui" data-testid="voice-service-kyc-tab-banner">
          <p className="font-semibold text-info-fg">
            Verification opened in a new tab
          </p>
          <p className="text-info-fg text-ui">
            Complete your verification in the opened tab, then return here and select &ldquo;I have finished. Refresh status&rdquo;.
          </p>
          <div className="pt-1">
            <a
              href={openedUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-meta font-semibold text-accent-fg hover:underline"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Reopen verification page in new tab
            </a>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <TactileButton
          size="md"
          variant="brand"
          disabled={starting || !canStart || legalName.trim().length < 2 || !businessType}
          loading={starting}
          onClick={start}
          icon={ExternalLink}
          className="w-full justify-center"
          data-testid="voice-service-kyc-start"
        >
          {starting ? 'Preparing…' : status?.status === 'pending' ? 'Continue verification' : 'Start verification'}
        </TactileButton>
        <button
          type="button"
          onClick={() => refresh(true)}
          disabled={loading}
          className="w-full min-h-[36px] inline-flex items-center justify-center gap-1.5 text-ui font-semibold text-accent-fg hover:underline py-1 disabled:opacity-60"
          data-testid="voice-service-kyc-refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          I have finished. Refresh status
        </button>
      </div>
    </div>
  );
}
