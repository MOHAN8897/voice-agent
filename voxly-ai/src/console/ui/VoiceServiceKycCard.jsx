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

  const refresh = useCallback(async () => {
    const current = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const next = await api.kyc.getVoiceStatus();
      if (current !== requestId.current) return;
      setStatus(next);
      if (next?.businessType) setBusinessType(next.businessType);
      if (next?.legalName) setLegalName(next.legalName);
      if (next?.approved) onApprovedRef.current?.(next);
    } catch (e) {
      if (current !== requestId.current) return;
      setError(e.message || 'Could not load phone service verification status.');
    } finally {
      if (current === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onResume = () => refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
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

  const start = async () => {
    setStarting(true);
    setError('');
    try {
      const result = await api.kyc.startVoiceSession({
        legal_name: legalName.trim(),
        business_type: businessType,
        return_url: window.location.href,
      });
      setStatus(result);
      if (result?.approved) {
        onApprovedRef.current?.(result);
        return;
      }
      if (!result?.sessionUrl) throw new Error('Verification could not start. Please try again.');
      window.location.assign(result.sessionUrl);
    } catch (e) {
      setError(e.message || 'Could not start phone service verification.');
    } finally {
      setStarting(false);
    }
  };

  if (status?.required === false) return null;

  if (loading && !status) {
    return (
      <div className="rounded-2xl border border-[#E4E2EB] bg-[#FAF9FD] p-6 space-y-4" aria-busy="true">
        <div className="flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-[#6344E7]" />
          <p className="text-sm text-[#524E5E]">Checking phone service verification…</p>
        </div>
      </div>
    );
  }

  if (status?.approved) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center space-y-2" data-testid="voice-service-kyc-approved">
        <BadgeCheck className="w-9 h-9 text-emerald-700 mx-auto" />
        <h3 className="text-base font-bold text-emerald-950">Phone service verified</h3>
        <p className="text-xs text-emerald-900">You can continue with your number purchase and live calls.</p>
      </div>
    );
  }

  const canStart = status?.configured === true && !error && !loading && !['creating', 'provisioning_unknown', 'credentials_lost'].includes(status?.status);

  return (
    <div className="rounded-2xl border border-[#E4E2EB] bg-gradient-to-b from-white to-[#FAF9FD] p-5 sm:p-6 space-y-5" data-testid="voice-service-kyc-card">
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-[#F3F0FF] border border-[#E4E2EB] flex items-center justify-center shrink-0">
          <Shield className="w-5 h-5 text-[#6344E7]" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-bold text-[#0F0E17]">Verify phone service</h3>
          <p className="mt-1 text-xs text-[#524E5E] leading-relaxed">
            Complete the secure identity check to activate phone numbers and live calls. The required documents depend on your legal entity type.
          </p>
          <p className="mt-2 text-[11px] font-semibold text-[#6344E7]">Status: {statusLabel(status?.status)}</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-[11px] font-semibold text-[#524E5E]">
          Legal entity type
          <select
            className="mt-1.5 block w-full rounded-lg border border-[#D8D5E2] bg-white px-3 py-2.5 text-sm text-[#0F0E17]"
            value={businessType}
            disabled={starting || status?.identityLocked}
            onChange={(event) => setBusinessType(event.target.value)}
            data-testid="voice-service-business-type"
          >
            <option value="">Select entity type</option>
            {BUSINESS_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-[11px] font-semibold text-[#524E5E]">
          Legal name
          <input
            className="mt-1.5 block w-full rounded-lg border border-[#D8D5E2] bg-white px-3 py-2.5 text-sm text-[#0F0E17]"
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

      {status?.verifications && Object.keys(status.verifications).length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Verification document status">
          {Object.entries(status.verifications).map(([key, value]) => (
            <span key={key} className="rounded-full border border-[#E4E2EB] bg-white px-2.5 py-1 text-[10px] text-[#524E5E]">
              {key.toUpperCase()}: {statusLabel(value)}
            </span>
          ))}
        </div>
      )}

      {status?.configured === false && (
        <p className="text-xs text-amber-800" role="status">Phone service verification is not available yet. Contact support to continue.</p>
      )}
      {error && <p className="text-xs text-red-800" role="alert" data-testid="voice-service-kyc-error">{error}</p>}

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
          onClick={refresh}
          disabled={loading}
          className="w-full inline-flex items-center justify-center gap-1.5 text-[11px] font-semibold text-[#6344E7] hover:underline py-1 disabled:opacity-60"
          data-testid="voice-service-kyc-refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          I finished — refresh status
        </button>
      </div>
    </div>
  );
}
