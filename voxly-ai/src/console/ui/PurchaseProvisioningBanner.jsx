import React, { useEffect, useState } from 'react';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';

const STORAGE_PURCHASE = 'voxly_pending_purchase';
const STORAGE_ASSIGN_AGENT = 'voxly_pending_assign_agent';

export function PurchaseProvisioningBanner() {
  const { loadWorkspaceData, assignNumberToAgent } = useWorkspace();
  const [message, setMessage] = useState(null);
  const [variant, setVariant] = useState('info');

  useEffect(() => {
    const purchaseId = sessionStorage.getItem(STORAGE_PURCHASE);
    if (!purchaseId || !api.getToken()) return;

    let attempts = 0;
    const maxAttempts = 24;

    const tick = async () => {
      attempts += 1;
      try {
        const row = await api.telephony.getPurchase(purchaseId);
        const status = row?.status || '';
        if (status === 'active' && row.phoneNumberId) {
          const agentId = sessionStorage.getItem(STORAGE_ASSIGN_AGENT);
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          if (agentId) {
            await assignNumberToAgent(row.phoneNumberId, agentId);
          }
          await loadWorkspaceData();
          setVariant('success');
          setMessage(`Number ${row.e164 || ''} is active and ready.`);
          return;
        }
        if (status === 'failed') {
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          setVariant('error');
          setMessage('Number provisioning failed. Check Stripe/Telnyx or contact support.');
          return;
        }
        setVariant('info');
        setMessage(`Provisioning your number… (${status || 'paid'})`);
        if (attempts < maxAttempts) {
          setTimeout(tick, 5000);
        } else {
          setMessage('Provisioning is taking longer than usual. Click Retry sync in the banner above.');
        }
      } catch (e) {
        if (attempts < maxAttempts) setTimeout(tick, 5000);
        else setMessage(e.message || 'Could not check purchase status');
      }
    };

    tick();
  }, [loadWorkspaceData, assignNumberToAgent]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === '1' && !sessionStorage.getItem(STORAGE_PURCHASE)) {
      setVariant('info');
      setMessage('Payment received. Syncing your workspace…');
      loadWorkspaceData?.();
    }
  }, [loadWorkspaceData]);

  if (!message) return null;

  const styles =
    variant === 'success'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
      : variant === 'error'
        ? 'border-red-200 bg-red-50 text-red-900'
        : 'border-blue-200 bg-blue-50 text-blue-900';

  const Icon = variant === 'success' ? CheckCircle2 : variant === 'error' ? AlertCircle : Loader2;

  return (
    <div className={`mb-4 rounded-xl border px-4 py-3 flex items-center gap-2 text-sm ${styles}`}>
      <Icon className={`w-4 h-4 shrink-0 ${variant === 'info' ? 'animate-spin' : ''}`} />
      <span>{message}</span>
    </div>
  );
}

export function stashPurchaseForRedirect(purchaseId, assignAgentId) {
  if (purchaseId) sessionStorage.setItem(STORAGE_PURCHASE, purchaseId);
  if (assignAgentId) sessionStorage.setItem(STORAGE_ASSIGN_AGENT, assignAgentId);
}
