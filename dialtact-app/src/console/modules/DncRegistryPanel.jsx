import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Plus,
  Search,
  RefreshCw,
  PhoneOff,
  UserCheck,
  History,
  AlertCircle,
  Trash2,
  CheckCircle2,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { Badge } from '../ui/StatusBadge';
import { relativeTime } from '../../lib/money';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { DncTableSkeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';
import { formatPhone } from '../../lib/phoneMask';

/**
 * DncRegistryPanel
 * Tenant-wide Do Not Call registry management with compliance audit log.
 * Authoritatively blocks dials across all agents and requires explicit re-consent for deactivation.
 */
export function DncRegistryPanel({ readOnly = false }) {
  const [subTab, setSubTab] = useState('active'); // 'active' | 'deactivated'
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [loadError, setLoadError] = useState('');
  const requestVersion = useRef(0);

  // Add Modal State
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [addMode, setAddMode] = useState('single'); // 'single' | 'bulk'
  const [singlePhone, setSinglePhone] = useState('');
  const [bulkPhones, setBulkPhones] = useState('');
  // Empty means "added by hand"; the request still falls back to manual_operator.
  const [addReason, setAddReason] = useState('');
  const [addBusy, setAddBusy] = useState(false);

  // Deactivate / Audit Modal State
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [removalReason, setRemovalReason] = useState('');
  const [reconsentConfirmed, setReconsentConfirmed] = useState(false);
  const [deactivateBusy, setDeactivateBusy] = useState(false);

  const fetchEntries = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true); setLoadError('');
    try {
      const res = await api.dnc.list({
        status: subTab === 'active' ? 'active' : 'inactive',
        search: search.trim(),
        page,
        limit: 50,
      });
      if (version !== requestVersion.current) return;
      setEntries(res.entries || []);
      setTotal(res.total || 0);
    } catch (err) {
      if (version !== requestVersion.current) return;
      setLoadError(err.message || 'Could not load the Do Not Call registry. Retry to refresh these results.');
      showToast(err.message || 'Could not load Do Not Call registry', 'error');
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [subTab, search, page]);

  useEffect(() => {
    fetchEntries();
    return () => { requestVersion.current += 1; };
  }, [fetchEntries]);

  // Handle Add Entry
  const handleAdd = async (e) => {
    e.preventDefault();
    if (readOnly || addBusy) return;
    setAddBusy(true);
    try {
      if (addMode === 'single') {
        const clean = singlePhone.trim();
        if (!clean) {
          showToast('Enter a valid phone number in international E.164 format', 'error');
          setAddBusy(false);
          return;
        }
        await api.dnc.add(clean, addReason || 'manual_operator');
        showToast(`Added ${formatPhone(clean) || clean} to Do Not Call registry`, 'success');
      } else {
        const list = bulkPhones
          .split(/\r?\n/)
          .map((p) => p.trim())
          .filter(Boolean);
        if (!list.length) {
          showToast('Paste at least one phone number', 'error');
          setAddBusy(false);
          return;
        }
        const res = await api.dnc.bulkAdd(list, addReason || 'bulk_upload');
        showToast(`Added ${res.added || list.length} numbers to Do Not Call registry`, 'success');
      }
      setIsAddOpen(false);
      setSinglePhone('');
      setBulkPhones('');
      fetchEntries();
    } catch (err) {
      showToast(err.message || 'Could not add to Do Not Call list', 'error');
    } finally {
      setAddBusy(false);
    }
  };

  // Handle Deactivate with Mandatory Audit Re-consent
  const handleDeactivate = async () => {
    if (readOnly || !deactivateTarget || removalReason.trim().length < 5 || !reconsentConfirmed || deactivateBusy) return;
    setDeactivateBusy(true);
    try {
      const phone = deactivateTarget.phoneE164 || deactivateTarget.phone_e164;
      await api.dnc.deactivate(phone, removalReason.trim(), true, deactivateTarget.addedAt || deactivateTarget.added_at || null);
      showToast(`Removed ${formatPhone(phone) || phone} from active Do Not Call list`, 'success');
      setDeactivateTarget(null);
      setRemovalReason('');
      setReconsentConfirmed(false);
      fetchEntries();
    } catch (err) {
      showToast(err.message || 'Failed to deactivate Do Not Call entry', 'error');
    } finally {
      setDeactivateBusy(false);
    }
  };

  const formatSource = (source) => {
    switch (source) {
      case 'opt_out':
      case 'call_opt_out':
        return 'Asked on a call';
      case 'bulk_upload':
        return 'Bulk upload';
      case 'operator_ui':
      case 'manual':
      default:
        return 'Added by hand';
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return '—';
    try {
      return new Date(isoStr).toLocaleString('en-IN');
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="space-y-6" data-testid="dnc-registry-panel">
      {loadError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-warning-line bg-warning-soft px-4 py-3 text-copy text-warning-fg"><span className="min-w-0">{loadError} The list below may be out of date.</span><TactileButton size="sm" variant="secondary" onClick={fetchEntries}>Retry</TactileButton></div>}
      <p className="text-ui text-fg-body max-w-3xl">
        Numbers on this list are never called by your campaigns. Check national DND preferences and
        consent separately through the official TRAI process.
      </p>
      {/* Sub-navigation & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Tab Switcher */}
        <div className="flex min-w-0 max-w-full overflow-x-auto no-scrollbar border-b border-line gap-6 text-ui font-medium">
          <button
            type="button"
            onClick={() => { setSubTab('active'); setPage(1); }}
className={`min-h-[40px] pb-2.5 -mb-px transition-colors border-b-2 flex items-center gap-1.5 whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t-control ${
              subTab === 'active'
                ? 'border-ink text-ink'
                : 'border-transparent text-fg-body hover:text-ink'
            }`}
            data-testid="dnc-tab-active"
          >
            <ShieldAlert className="w-4 h-4" />
            On the list <span className="font-mono tabular-nums text-fg-muted">{subTab === 'active' ? total : '—'}</span>
          </button>
          <button
            type="button"
            onClick={() => { setSubTab('deactivated'); setPage(1); }}
className={`min-h-[40px] pb-2.5 -mb-px transition-colors border-b-2 flex items-center gap-1.5 whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t-control ${
              subTab === 'deactivated'
                ? 'border-ink text-ink'
                : 'border-transparent text-fg-body hover:text-ink'
            }`}
            data-testid="dnc-tab-deactivated"
          >
            <History className="w-4 h-4" />
            Removed (history) <span className="font-mono tabular-nums text-fg-muted">{subTab === 'deactivated' ? total : '—'}</span>
          </button>
        </div>

        {/* Action button */}
        <TactileButton
          disabled={readOnly}
          onClick={() => setIsAddOpen(true)}
          variant="primary"
          icon={Plus}
          size="sm"
          data-testid="add-dnc-button"
        >
          Add number
        </TactileButton>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex items-center gap-2">
        <label className="relative flex-1 min-w-0 max-w-sm">
          <span className="sr-only">Search phone numbers</span>
          <Search className="w-4 h-4 text-fg-subtle absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
          <input
            type="text"
            placeholder="Search phone numbers"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            data-testid="dnc-search-input"
            className="w-full text-base sm:text-ui pl-9 pr-4 py-2 min-h-[44px] sm:min-h-[36px] bg-surface border border-line rounded-control focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle"
          />
        </label>
        <button
          type="button"
          onClick={() => fetchEntries()}
          className="p-2 min-w-[44px] min-h-[44px] sm:min-w-[36px] sm:min-h-[36px] flex items-center justify-center text-fg-body hover:text-ink bg-surface hover:bg-canvas rounded-control border border-line transition-colors shrink-0"
          title="Refresh list"
          aria-label="Refresh list"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Registry Table */}
      <SolidCard padding="p-0" className="overflow-hidden min-w-0">
        {loading && entries.length === 0 ? (
          <DncTableSkeleton rows={5} />
        ) : entries.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <span className="mx-auto mb-1 flex h-10 w-10 items-center justify-center rounded-control bg-surface-subtle" aria-hidden="true">
              <PhoneOff className="w-5 h-5 text-fg-body" />
            </span>
            <h4 className="text-title text-ink">
              {subTab === 'active' ? 'No numbers on the list' : 'No removed numbers'}
            </h4>
            <p className="text-ui text-fg-muted max-w-sm mx-auto">
              {subTab === 'active'
                ? 'Numbers that ask not to be called, or that you add, will appear here and are skipped by every campaign.'
                : 'Numbers you remove after the person agrees to calls again are kept here as a record.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto touch-pan-x">
            <table className="w-full min-w-[720px] text-left border-collapse text-ui">
              <thead>
                <tr className="border-b border-line bg-canvas text-meta text-fg-muted font-medium">
                  <th className="py-2.5 px-4">Phone number</th>
                  <th className="py-2.5 px-4">Source</th>
                  <th className="py-2.5 px-4">Reason or note</th>
                  <th className="py-2.5 px-4">Added</th>
                  {subTab === 'deactivated' && (
                    <>
                      <th className="py-2.5 px-4">Removed</th>
                      <th className="py-2.5 px-4">Why removed</th>
                      <th className="py-2.5 px-4">Consent</th>
                    </>
                  )}
                  {subTab === 'active' && <th className="py-2.5 px-4 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {entries.map((item) => {
                  const phone = item.phoneE164 || item.phone_e164;
                  return (
                    <tr
                      key={item.id || phone}
                      className="hover:bg-canvas transition-colors text-ink"
                      data-testid={`dnc-row-${phone}`}
                    >
                      {/* Blocked numbers read red at a glance; the badge says it in words too (never colour alone). */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        {subTab === 'active' ? (
                          <span className="inline-flex items-center gap-2">
                            <span className="font-mono tabular-nums font-semibold text-danger-fg" data-testid="dnc-phone" title={phone}>{formatPhone(phone) || phone}</span>
                            <Badge tone="danger" size="xs" data-testid="dnc-blocked-badge">
                              <PhoneOff className="h-3 w-3" aria-hidden="true" />
                              Do not call
                            </Badge>
                          </span>
                        ) : (
                          <span className="font-mono tabular-nums font-semibold text-ink" data-testid="dnc-phone" title={phone}>{formatPhone(phone) || phone}</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <Badge tone="neutral">{formatSource(item.source)}</Badge>
                      </td>
                      <td className="py-3 px-4 text-fg-body truncate max-w-xs" title={item.reason || undefined}>{item.reason === 'manual_operator' ? 'Added by hand' : item.reason || '—'}</td>
                      <td className="py-3 px-4 text-fg-body whitespace-nowrap" title={formatDate(item.addedAt || item.added_at)}>{relativeTime(item.addedAt || item.added_at) || '—'}</td>

                      {subTab === 'deactivated' && (
                        <>
                          <td className="py-3 px-4 text-fg-body whitespace-nowrap" title={formatDate(item.removedAt || item.removed_at)}>{relativeTime(item.removedAt || item.removed_at) || '—'}</td>
                          <td className="py-3 px-4 font-medium text-ink max-w-xs truncate" title={item.removalReason || item.removal_reason || undefined}>
                            {item.removalReason || item.removal_reason || '—'}
                          </td>
                          <td className="py-3 px-4">
                            <Badge tone="success">
                              <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                              Agreed again
                            </Badge>
                          </td>
                        </>
                      )}

                      {subTab === 'active' && (
                        <td className="py-3 px-4 text-right">
                          <TactileButton
                            variant="ghost"
                            size="xs"
                            icon={Trash2}
                            onClick={() => {
                              if (readOnly) return;
                              setDeactivateTarget(item);
                              setRemovalReason('');
                              setReconsentConfirmed(false);
                            }}
                            disabled={readOnly}
                            data-testid={`deactivate-dnc-${phone}`}
                          >
                            Remove from list
                          </TactileButton>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SolidCard>

      {/* Add to Do Not Call Modal */}
      <Modal
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        title="Add to Do Not Call list"
        subtitle="Numbers on this list are never called by any campaign in this workspace."
        maxWidth="max-w-lg"
      >
        <form onSubmit={handleAdd} className="space-y-4">
          <div className="inline-flex items-center gap-0.5 rounded-control border border-line bg-surface-subtle p-0.5" role="tablist" aria-label="How to add">
            <button
              type="button"
              role="tab"
              aria-selected={addMode === 'single'}
              onClick={() => setAddMode('single')}
              className={`rounded-[8px] px-3 py-1.5 min-h-[32px] text-ui font-medium transition-colors ${
                addMode === 'single' ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
              }`}
            >
              One number
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={addMode === 'bulk'}
              onClick={() => setAddMode('bulk')}
              className={`rounded-[8px] px-3 py-1.5 min-h-[32px] text-ui font-medium transition-colors ${
                addMode === 'bulk' ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
              }`}
            >
              Paste many
            </button>
          </div>

          {addMode === 'single' ? (
            <div>
              <label htmlFor="add-dnc-single" className="block text-ui font-medium text-ink mb-1">
                Phone number, with country code
              </label>
              <input
                type="text"
                id="add-dnc-single"
                placeholder="+919876543210"
                value={singlePhone}
                onChange={(e) => setSinglePhone(e.target.value)}
                data-testid="add-dnc-single-phone"
                className="w-full text-base sm:text-ui px-3.5 py-2.5 min-h-[44px] sm:min-h-[38px] rounded-control bg-surface border border-line focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle font-mono tabular-nums"
              />
            </div>
          ) : (
            <div>
              <label htmlFor="add-dnc-bulk" className="block text-ui font-medium text-ink mb-1">
                Phone numbers, one per line
              </label>
              <textarea
                id="add-dnc-bulk"
                placeholder={'+919876543210\n+15551234567'}
                value={bulkPhones}
                onChange={(e) => setBulkPhones(e.target.value)}
                rows={4}
                data-testid="add-dnc-bulk-phones"
                className="w-full text-base sm:text-ui px-3.5 py-2.5 min-h-[44px] sm:min-h-[38px] rounded-control bg-surface border border-line focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle font-mono tabular-nums"
              />
            </div>
          )}

          <div>
            <label htmlFor="add-dnc-reason" className="block text-ui font-medium text-ink mb-1">
              Reason or note <span className="font-normal text-fg-muted">(optional)</span>
            </label>
            <input
              id="add-dnc-reason"
              type="text"
              placeholder="For example: asked not to be called again"
              value={addReason}
              onChange={(e) => setAddReason(e.target.value)}
              className="w-full text-base sm:text-ui px-3.5 py-2.5 min-h-[44px] sm:min-h-[38px] rounded-control bg-surface border border-line focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-line">
            <TactileButton type="button" variant="ghost" size="sm" onClick={() => setIsAddOpen(false)}>
              Cancel
            </TactileButton>
            <TactileButton
              type="submit"
              variant="primary"
              size="sm"
              loading={addBusy}
              data-testid="add-dnc-submit-btn"
            >
              Add to list
            </TactileButton>
          </div>
        </form>
      </Modal>

      {/* Deactivation Audit Modal */}
      <Modal
        isOpen={Boolean(deactivateTarget)}
        onClose={() => { if (!deactivateBusy) setDeactivateTarget(null); }}
        title="Remove from Do Not Call list"
        subtitle={`Confirm that ${formatPhone(deactivateTarget?.phoneE164 || deactivateTarget?.phone_e164) || 'this number'} has agreed to be called again`}
        maxWidth="max-w-lg"
      >
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 p-3.5 bg-warning-soft border border-warning-line text-warning-fg rounded-control text-ui">
            <AlertCircle className="w-4 h-4 text-warning-fg shrink-0 mt-0.5" aria-hidden="true" />
            <p>
              <strong className="font-semibold">Before you remove it:</strong> campaigns will be able to call this number again. Write down why, and confirm the person has clearly agreed to be called.
            </p>
          </div>

          <div>
            <label htmlFor="dnc-removal-reason" className="block text-ui font-medium text-ink mb-1">
              Why are you removing it? <span className="font-normal text-fg-muted">(at least 5 characters)</span>
            </label>
            <input
              id="dnc-removal-reason"
              type="text"
              placeholder="For example: signed up again through our website"
              value={removalReason}
              maxLength={1000}
              onChange={(e) => setRemovalReason(e.target.value)}
              data-testid="dnc-deactivate-reason-input"
              className="w-full text-base sm:text-ui px-3.5 py-2.5 min-h-[44px] sm:min-h-[38px] rounded-control bg-surface border border-line focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle"
            />
          </div>

          {/* Mandatory Re-consent Checkbox */}
          <label className="flex items-start gap-3 p-3.5 rounded-control border border-line hover:bg-canvas transition-colors cursor-pointer select-none">
            <input
              type="checkbox"
              checked={reconsentConfirmed}
              onChange={(e) => setReconsentConfirmed(e.target.checked)}
              data-testid="dnc-reconsent-checkbox"
              className="mt-0.5 w-4 h-4 shrink-0 rounded accent-accent focus:ring-accent border-line-strong"
            />
            <span className="text-ui font-medium text-ink">
              I confirm that this contact has provided new authorization to receive calls.
            </span>
          </label>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-line">
            <TactileButton type="button" variant="ghost" size="sm" onClick={() => setDeactivateTarget(null)}>
              Cancel
            </TactileButton>
            <TactileButton
              type="button"
              variant="primary"
              size="sm"
              disabled={readOnly || removalReason.trim().length < 5 || !reconsentConfirmed || deactivateBusy}
              loading={deactivateBusy}
              onClick={handleDeactivate}
              data-testid="dnc-deactivate-confirm-btn"
            >
              Confirm removal
            </TactileButton>
          </div>
        </div>
      </Modal>
    </div>
  );
}
