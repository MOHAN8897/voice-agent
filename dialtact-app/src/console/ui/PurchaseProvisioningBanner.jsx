import React, { useEffect, useState } from 'react';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { PURCHASE_COPY, purchaseOutcomeMessage } from '../lib/numberPurchaseCopy';

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
        if (status === 'failed' || status === 'refunded' || status === 'needs_attention') {
          sessionStorage.removeItem(STORAGE_PURCHASE);
          sessionStorage.removeItem(STORAGE_ASSIGN_AGENT);
          // Calm, not alarming: the message says where the money is.
          setVariant('warning');
          setMessage(purchaseOutcomeMessage(row));
          if (status !== 'needs_attention') loadWorkspaceData?.();
          return;
        }
        setVariant('info');
        setMessage(`Setting up ${row?.e164 ? `number ${row.e164}` : 'your number'}. This usually takes under a minute.`);
        if (attempts < maxAttempts) {
          setTimeout(tick, 5000);
        } else {
          setMessage(PURCHASE_COPY.stillActivating);
        }
      } catch {
        if (attempts < maxAttempts) setTimeout(tick, 5000);
        else setMessage(PURCHASE_COPY.checkingFailed);
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
        : variant === 'warning'
          ? 'border-warning-line bg-warning-soft text-warning-fg'
        : 'border-info-line bg-info-soft text-info-fg';

  const Icon = variant === 'success' ? CheckCircle2 : variant === 'error' || variant === 'warning' ? AlertCircle : Loader2;

  return (
    <div className={`mb-4 rounded-card border px-4 py-3 flex items-start gap-2 text-copy ${styles}`} role="status" data-testid="purchase-provisioning-banner">
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${variant === 'info' ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function stashPurchaseForRedirect(purchaseId, assignAgentId) {
  if (purchaseId) sessionStorage.setItem(STORAGE_PURCHASE, purchaseId);
  if (assignAgentId) sessionStorage.setItem(STORAGE_ASSIGN_AGENT, assignAgentId);
}
