import React, { useState, useEffect, useCallback } from 'react';
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
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { DncTableSkeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';

/**
 * DncRegistryPanel
 * Tenant-wide Do Not Call registry management with compliance audit log.
 * Authoritatively blocks dials across all agents and requires explicit re-consent for deactivation.
 */
export function DncRegistryPanel() {
  const [subTab, setSubTab] = useState('active'); // 'active' | 'deactivated'
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // Add Modal State
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [addMode, setAddMode] = useState('single'); // 'single' | 'bulk'
  const [singlePhone, setSinglePhone] = useState('');
  const [bulkPhones, setBulkPhones] = useState('');
  const [addReason, setAddReason] = useState('manual_operator');
  const [addBusy, setAddBusy] = useState(false);

  // Deactivate / Audit Modal State
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [removalReason, setRemovalReason] = useState('');
  const [reconsentConfirmed, setReconsentConfirmed] = useState(false);
  const [deactivateBusy, setDeactivateBusy] = useState(false);

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.dnc.list({
        status: subTab === 'active' ? 'active' : 'inactive',
        search: search.trim(),
        page,
        limit: 50,
      });
      setEntries(res.entries || []);
      setTotal(res.total || 0);
    } catch (err) {
      showToast(err.message || 'Could not load Do Not Call registry', 'error');
    } finally {
      setLoading(false);
    }
  }, [subTab, search, page]);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  // Handle Add Entry
  const handleAdd = async (e) => {
    e.preventDefault();
    setAddBusy(true);
    try {
      if (addMode === 'single') {
        const clean = singlePhone.trim();
        if (!clean) {
          showToast('Enter a valid phone number in E.164 (+1...) format', 'error');
          setAddBusy(false);
          return;
        }
        await api.dnc.add(clean, addReason || 'manual_operator');
        showToast(`Added ${clean} to Do Not Call registry`, 'success');
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
    if (!deactivateTarget || !removalReason.trim() || !reconsentConfirmed || deactivateBusy) return;
    setDeactivateBusy(true);
    try {
      const phone = deactivateTarget.phoneE164 || deactivateTarget.phone_e164;
      await api.dnc.deactivate(phone, removalReason.trim(), true);
      showToast(`Removed ${phone} from active Do Not Call list`, 'success');
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
        return 'Live Call Opt-Out';
      case 'bulk_upload':
        return 'Bulk Upload';
      case 'operator_ui':
      case 'manual':
      default:
        return 'Manual Operator';
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return '—';
    try {
      return new Date(isoStr).toLocaleString();
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="space-y-6" data-testid="dnc-registry-panel">
      {/* Sub-navigation & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Tab Switcher */}
        <div className="flex border-b border-[#E4E2EB] gap-6 text-xs font-semibold">
          <button
            type="button"
            onClick={() => { setSubTab('active'); setPage(1); }}
            className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
              subTab === 'active'
                ? 'border-[#FF5C35] text-[#FF5C35]'
                : 'border-transparent text-[#524E5E] hover:text-[#0F0E17]'
            }`}
            data-testid="dnc-tab-active"
          >
            <ShieldAlert className="w-4 h-4" />
            Active DND ({subTab === 'active' ? total : '—'})
          </button>
          <button
            type="button"
            onClick={() => { setSubTab('deactivated'); setPage(1); }}
            className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
              subTab === 'deactivated'
                ? 'border-[#FF5C35] text-[#FF5C35]'
                : 'border-transparent text-[#524E5E] hover:text-[#0F0E17]'
            }`}
            data-testid="dnc-tab-deactivated"
          >
            <History className="w-4 h-4" />
            Deactivated / Audit History ({subTab === 'deactivated' ? total : '—'})
          </button>
        </div>

        {/* Action button */}
        <TactileButton
          onClick={() => setIsAddOpen(true)}
          variant="primary"
          icon={Plus}
          size="sm"
          data-testid="add-dnc-button"
        >
          Add to Do Not Call
        </TactileButton>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 text-[#8C879A] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search phone numbers..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            data-testid="dnc-search-input"
            className="w-full text-xs pl-9 pr-4 py-2 bg-white border border-[#E4E2EB] rounded-xl focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
          />
        </div>
        <button
          type="button"
          onClick={() => fetchEntries()}
          className="p-2 text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] rounded-xl border border-[#E4E2EB] transition-colors"
          title="Refresh registry"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Registry Table */}
      <SolidCard className="p-0 overflow-hidden">
        {loading && entries.length === 0 ? (
          <DncTableSkeleton rows={5} />
        ) : entries.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <PhoneOff className="w-8 h-8 text-[#8C879A] mx-auto opacity-50" />
            <h4 className="text-sm font-bold text-[#0F0E17]">
              {subTab === 'active' ? 'No active Do Not Call numbers' : 'No deactivated audit records'}
            </h4>
            <p className="text-xs text-[#524E5E] max-w-sm mx-auto">
              {subTab === 'active'
                ? 'Numbers opted out during live calls or added manually will appear here and be excluded from all campaigns.'
                : 'Deactivated numbers with audit re-consent verification will be preserved here.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[#524E5E] font-semibold">
                  <th className="py-3 px-4">Phone Number</th>
                  <th className="py-3 px-4">Source</th>
                  <th className="py-3 px-4">Reason / Notes</th>
                  <th className="py-3 px-4">Date Added</th>
                  {subTab === 'deactivated' && (
                    <>
                      <th className="py-3 px-4">Deactivated At</th>
                      <th className="py-3 px-4">Removal Reason</th>
                      <th className="py-3 px-4">Re-consent</th>
                    </>
                  )}
                  {subTab === 'active' && <th className="py-3 px-4 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {entries.map((item) => {
                  const phone = item.phoneE164 || item.phone_e164;
                  return (
                    <tr
                      key={item.id || phone}
                      className="hover:bg-[#FAF9FD] transition-colors text-[#0F0E17]"
                      data-testid={`dnc-row-${phone}`}
                    >
                      <td className="py-3 px-4 font-mono font-semibold">{phone}</td>
                      <td className="py-3 px-4">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
                          {formatSource(item.source)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-[#524E5E] truncate max-w-xs">{item.reason || '—'}</td>
                      <td className="py-3 px-4 text-[#524E5E]">{formatDate(item.addedAt || item.added_at)}</td>

                      {subTab === 'deactivated' && (
                        <>
                          <td className="py-3 px-4 text-[#524E5E]">{formatDate(item.removedAt || item.removed_at)}</td>
                          <td className="py-3 px-4 font-medium text-[#0F0E17] max-w-xs truncate">
                            {item.removalReason || item.removal_reason || '—'}
                          </td>
                          <td className="py-3 px-4">
                            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-semibold">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                              Re-consented
                            </span>
                          </td>
                        </>
                      )}

                      {subTab === 'active' && (
                        <td className="py-3 px-4 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              setDeactivateTarget(item);
                              setRemovalReason('');
                              setReconsentConfirmed(false);
                            }}
                            data-testid={`deactivate-dnc-${phone}`}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors border border-transparent hover:border-red-200"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Deactivate
                          </button>
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
        title="Add to Do Not Call Registry"
        subtitle="Numbers on this list are permanently excluded from all outbound campaigns for this tenant."
        maxWidth="max-w-lg"
      >
        <form onSubmit={handleAdd} className="space-y-4">
          <div className="flex border-b border-[#E4E2EB] gap-4 text-xs font-semibold mb-2">
            <button
              type="button"
              onClick={() => setAddMode('single')}
              className={`pb-2 border-b-2 ${
                addMode === 'single'
                  ? 'border-[#FF5C35] text-[#FF5C35]'
                  : 'border-transparent text-[#524E5E]'
              }`}
            >
              Single Number
            </button>
            <button
              type="button"
              onClick={() => setAddMode('bulk')}
              className={`pb-2 border-b-2 ${
                addMode === 'bulk'
                  ? 'border-[#FF5C35] text-[#FF5C35]'
                  : 'border-transparent text-[#524E5E]'
              }`}
            >
              Bulk Paste
            </button>
          </div>

          {addMode === 'single' ? (
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                Phone Number (E.164)
              </label>
              <input
                type="text"
                placeholder="+15551234567"
                value={singlePhone}
                onChange={(e) => setSinglePhone(e.target.value)}
                data-testid="add-dnc-single-phone"
                className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
              />
            </div>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                Paste Phone Numbers (one per line)
              </label>
              <textarea
                placeholder={'+15551234567\n+919876543210'}
                value={bulkPhones}
                onChange={(e) => setBulkPhones(e.target.value)}
                rows={4}
                data-testid="add-dnc-bulk-phones"
                className="w-full text-xs font-mono px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
              Reason / Source Note
            </label>
            <input
              type="text"
              placeholder="manual_operator"
              value={addReason}
              onChange={(e) => setAddReason(e.target.value)}
              className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#E4E2EB]">
            <button
              type="button"
              onClick={() => setIsAddOpen(false)}
              className="px-4 py-2 text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17]"
            >
              Cancel
            </button>
            <TactileButton
              type="submit"
              variant="primary"
              size="sm"
              loading={addBusy}
              data-testid="add-dnc-submit-btn"
            >
              Add to Registry
            </TactileButton>
          </div>
        </form>
      </Modal>

      {/* Deactivation Audit Modal */}
      <Modal
        isOpen={Boolean(deactivateTarget)}
        onClose={() => setDeactivateTarget(null)}
        title="Remove from Do Not Call Registry"
        subtitle={`Confirm re-consent authorization for ${deactivateTarget?.phoneE164 || deactivateTarget?.phone_e164}`}
        maxWidth="max-w-lg"
      >
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 p-3.5 bg-amber-500/10 border border-amber-500/20 text-amber-900 rounded-xl text-xs leading-relaxed">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p>
              <strong>Regulatory Notice:</strong> Removing a number enables campaigns to place calls to this phone again. To protect against compliance violations, you must document the reason and attest that the recipient has given new affirmative consent.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
              Removal reason (Required, min 5 chars)
            </label>
            <input
              type="text"
              placeholder="e.g. Recipient requested re-subscription via web form"
              value={removalReason}
              onChange={(e) => setRemovalReason(e.target.value)}
              data-testid="dnc-deactivate-reason-input"
              className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
            />
          </div>

          {/* Mandatory Re-consent Checkbox */}
          <label className="flex items-start gap-3 p-3.5 rounded-xl border border-[#E4E2EB] hover:bg-[#FAF9FD] transition-colors cursor-pointer select-none">
            <input
              type="checkbox"
              checked={reconsentConfirmed}
              onChange={(e) => setReconsentConfirmed(e.target.checked)}
              data-testid="dnc-reconsent-checkbox"
              className="mt-0.5 w-4 h-4 rounded text-[#FF5C35] focus:ring-[#FF5C35] border-[#D1CFDB]"
            />
            <span className="text-xs font-medium text-[#0F0E17]">
              I confirm that this contact has provided new authorization to receive calls.
            </span>
          </label>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#E4E2EB]">
            <button
              type="button"
              onClick={() => setDeactivateTarget(null)}
              className="px-4 py-2 text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17]"
            >
              Cancel
            </button>
            <TactileButton
              type="button"
              variant="primary"
              size="sm"
              disabled={removalReason.trim().length < 5 || !reconsentConfirmed || deactivateBusy}
              loading={deactivateBusy}
              onClick={handleDeactivate}
              data-testid="dnc-deactivate-confirm-btn"
            >
              Confirm Deactivation
            </TactileButton>
          </div>
        </div>
      </Modal>
    </div>
  );
}
