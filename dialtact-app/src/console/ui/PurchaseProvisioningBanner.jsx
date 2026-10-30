import React, { useEffect, useState } from 'react';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { statusWord } from '../../lib/internalLabels';

const STORAGE_PURCHASE = 'dialtact_pending_purchase';
const STORAGE_ASSIGN_AGENT = 'dialtact_pending_assign_agent';

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
        if (
          (status === 'active' || status === 'provisioned') &&
          (row.phoneNumberId || status === 'provisioned')
        ) {
          const agentId = sessionStorage.getItem(STORAGE_ASSIGN_AGENT);
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          if (row.phoneNumberId) {
            if (agentId) {
              await assignNumberToAgent(row.phoneNumberId, agentId);
            } else if (row.assignAgentId) {
              await assignNumberToAgent(row.phoneNumberId, row.assignAgentId);
            }
          }
          await loadWorkspaceData();
          setVariant('success');
          setMessage(
            row.phoneNumberId || row.e164
              ? `Number ${row.e164 || ''} is active and ready.`
              : 'Number purchase completed.'
          );
          return;
        }
        if (status === 'failed') {
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          setVariant('error');
          setMessage('We could not set up your number. Check your wallet and try again, or contact support.');
          return;
        }
        if (status === 'needs_attention') {
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          setVariant('error');
          setMessage('Your number needs help from support to finish setting up. Contact support before buying another one.');
          return;
        }
        setVariant('info');
        setMessage(`Setting up your number… (${statusWord(status || 'paid').label})`);
        if (attempts < maxAttempts) {
          setTimeout(tick, 5000);
        } else {
          setMessage('Setting up your number is taking longer than usual. Use Retry sync in the banner above.');
        }
      } catch (e) {
        if (attempts < maxAttempts) setTimeout(tick, 5000);
        else setMessage(e.message || 'We could not check on your number purchase.');
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
      ? 'border-success-line bg-success-soft text-success-fg'
      : variant === 'error'
        ? 'border-danger-line bg-danger-soft text-danger-fg'
        : 'border-info-line bg-info-soft text-info-fg';

  const Icon = variant === 'success' ? CheckCircle2 : variant === 'error' ? AlertCircle : Loader2;

  return (
    <div className={`mb-4 rounded-card border px-4 py-3 flex items-start gap-2 text-copy ${styles}`} role="status">
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${variant === 'info' ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function stashPurchaseForRedirect(purchaseId, assignAgentId) {
  if (purchaseId) sessionStorage.setItem(STORAGE_PURCHASE, purchaseId);
  if (assignAgentId) sessionStorage.setItem(STORAGE_ASSIGN_AGENT, assignAgentId);
}
