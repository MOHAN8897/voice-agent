import React, { useState, useEffect } from 'react';
import {
  Phone,
  Plus,
  CheckCircle2,
  X,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { api } from '../../services/api';
import { VerifyIdentityCard } from '../ui/VerifyIdentityCard';
import { CatalogSkeleton } from '../ui/Skeleton';

const FALLBACK_COUNTRIES = [
  { code: 'US', name: 'United States', dial: '+1' },
  { code: 'GB', name: 'United Kingdom', dial: '+44' },
  { code: 'CA', name: 'Canada', dial: '+1' },
  { code: 'AU', name: 'Australia', dial: '+61' },
  { code: 'IE', name: 'Ireland', dial: '+353' },
  { code: 'NZ', name: 'New Zealand', dial: '+64' },
  { code: 'SG', name: 'Singapore', dial: '+65' },
  { code: 'ZA', name: 'South Africa', dial: '+27' },
  { code: 'PH', name: 'Philippines', dial: '+63' },
  { code: 'IN', name: 'India', dial: '+91' },
];

export function PhoneNumbersModule({ isBuyModalOpen, onCloseBuyModal, onOpenBuyModal, onNavigate }) {
  const {
    phoneNumbers,
    agents,
    availableCatalog,
    buyPhoneNumber,
    assignNumberToAgent,
    releasePhoneNumber,
    buyNumberPreselectedAgent,
    reloadCatalog,
    updateNumberRouting,
    wallet,
    refreshWallet,
    isLoading,
    openAddFunds,
  } = useWorkspace();

  // Buy Modal Form State — default US for English-speaking SaaS buyers.
  const [selectedCountry, setSelectedCountry] = useState('US');
  const [countries, setCountries] = useState(FALLBACK_COUNTRIES);
  const [selectedType, setSelectedType] = useState('Local DID');
  const [searchAreaCode, setSearchAreaCode] = useState('');
  const [targetAgentId, setTargetAgentId] = useState(buyNumberPreselectedAgent || '');
  const [purchasedSuccess, setPurchasedSuccess] = useState(null);
  const [buyError, setBuyError] = useState(null);
  const [buying, setBuying] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [kycApproved, setKycApproved] = useState(false);

  useEffect(() => {
    if (!isBuyModalOpen) return;
    setBuyError(null);
    setCatalogLoading(true);
    setCatalogError(null);
    reloadCatalog?.(selectedCountry)
      .catch((e) => setCatalogError(e.message || 'Could not load numbers for this country'))
      .finally(() => setCatalogLoading(false));
  }, [isBuyModalOpen, selectedCountry, reloadCatalog]);

  // Refresh KYC every time the buy modal opens — status can change outside this tab.
  useEffect(() => {
    if (!isBuyModalOpen) return undefined;
    let cancelled = false;
    api.kyc
      .getStatus()
      .then((st) => {
        if (cancelled) return;
        setKycApproved(Boolean(st?.approved));
      })
      .catch(() => {
        if (!cancelled) setKycApproved(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isBuyModalOpen]);

  useEffect(() => {
    let cancelled = false;
    api.telephony
      .getCountries()
      .then((data) => {
        if (cancelled) return;
        if (data.countries?.length) setCountries(data.countries);
        if (data.default) setSelectedCountry((prev) => prev || data.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Inline alerts should not sit forever — toast pattern: 5s, dismissible.
  useEffect(() => {
    if (!buyError) return undefined;
    const id = window.setTimeout(() => setBuyError(null), 5000);
    return () => window.clearTimeout(id);
  }, [buyError]);

  useEffect(() => {
    if (!catalogError) return undefined;
    const id = window.setTimeout(() => setCatalogError(null), 5000);
    return () => window.clearTimeout(id);
  }, [catalogError]);

  useEffect(() => {
    if (buyNumberPreselectedAgent) setTargetAgentId(buyNumberPreselectedAgent);
  }, [buyNumberPreselectedAgent]);

  const unassignedCount = phoneNumbers.filter((n) => !n.assignedAgentId).length;
  const assignedCount = phoneNumbers.length - unassignedCount;
  const monthlyRentalUsd = phoneNumbers.reduce(
    (sum, n) => sum + (Number(n.monthlyCost) || 0),
    0
  );
  const balanceUsd = Number(wallet?.balanceUsd) || 0;

  // Price and wallet top-up floor come from the server so the console can never
  // quote something `/api/telephony/buy` or `/api/billing/topup` would reject.
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.billing
      .getCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  // USD is the only quoted currency. A missing catalog means we do not know the
  // price, so we must not invent one — the buy button stays honest by asking the
  // server, which is the authority anyway.
  const numberPriceUsd = Number(catalog?.rates?.numberMonthlyUsd);
  const priceKnown = Number.isFinite(numberPriceUsd) && numberPriceUsd > 0;
  const canAffordNumber = priceKnown && balanceUsd >= numberPriceUsd;

  const filteredCatalog = availableCatalog.filter((item) => {
    const cc = (item.country || '').toUpperCase();
    const matchesCountry = cc === selectedCountry.toUpperCase();
    const matchesType = selectedType === 'All' || !item.type || item.type === selectedType;
    const matchesArea =
      !searchAreaCode ||
      (item.areaCode && item.areaCode.includes(searchAreaCode)) ||
      (item.number && item.number.includes(searchAreaCode));
    return matchesCountry && matchesType && matchesArea;
  });

  const handleBuyNumber = async (catalogItem) => {
    setBuyError(null);
    if (!kycApproved) {
      try {
        const st = await api.kyc.getStatus();
        if (!st?.approved) {
          setKycApproved(false);
          showToast('Complete identity verification before buying a number', 'error', 5000);
          return;
        }
        setKycApproved(true);
      } catch {
        /* server still enforces KYC on /buy */
      }
    }
    if (priceKnown && balanceUsd < numberPriceUsd) {
      const msg = `A phone number costs $${numberPriceUsd.toFixed(
        2
      )} per month. Add credit to your wallet to buy one.`;
      setBuyError(msg);
      return;
    }
    setBuying(true);
    setPurchasedSuccess(null);
    try {
      const bought = await buyPhoneNumber(catalogItem, targetAgentId || null);
      if (bought?.checkoutUrl) {
        return;
      }
      if (bought?.ok === false) {
        const failed =
          bought.failureReason === 'pending'
            ? 'The order is still being placed. It will appear in your lines shortly.'
            : bought.failureReason === 'carrier_balance_exhausted'
              ? 'Phone numbers are temporarily unavailable. Your wallet was not charged.'
              : 'Purchase failed — the number could not be provisioned. Your wallet has been refunded.';
        setBuyError(failed);
        if (bought.failureReason !== 'pending') await refreshWallet?.();
        return;
      }
      setPurchasedSuccess(catalogItem.formatted || catalogItem.number);
      showToast('Number purchased — provisioning to your workspace', 'success', 5000);
      await refreshWallet?.();
      setTimeout(() => {
        setPurchasedSuccess(null);
        onCloseBuyModal();
      }, 1800);
    } catch (e) {
      if (e.status === 402 || e.code === 'insufficient_balance') {
        const msg = priceKnown
          ? `${e.message} A phone number costs $${numberPriceUsd.toFixed(2)} per month.`
          : e.message;
        setBuyError(msg);
        await refreshWallet?.();
      } else if (e.status === 403 || e.code === 'kyc_required') {
        setKycApproved(false);
        setBuyError('Verify your identity to buy a phone number.');
      } else if (e.code === 'carrier_balance_exhausted' || e.status === 503) {
        setBuyError(
          e.message ||
            'Phone numbers are temporarily unavailable. Your wallet was not charged.'
        );
      } else {
        setBuyError(e.message || 'Could not start number purchase');
      }
    } finally {
      setBuying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Phone lines ({phoneNumbers.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5">
            Buy a number and connect it to an AI agent. Rental is billed monthly; call time is billed
            from your wallet.
          </p>
        </div>

        <TactileButton
          onClick={onOpenBuyModal}
          variant="primary"
          icon={Plus}
          size="md"
        >
          Buy Phone Number
        </TactileButton>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Owned lines</div>
          <div className="text-2xl font-bold text-[#0F0E17]">{phoneNumbers.length}</div>
        </SolidCard>
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Available to assign</div>
          <div className="text-2xl font-bold text-[#047857]">{unassignedCount}</div>
        </SolidCard>
        <SolidCard className="p-4">
          <div className="text-[10px] font-bold text-[#8C879A] uppercase">Linked to agents</div>
          <div className="text-2xl font-bold text-[#6344E7]">{assignedCount}</div>
        </SolidCard>
      </div>

      {/* Money the current lines cost per month, from the server's rates. */}
      <div className="text-[11px] text-[#524E5E]">
        Monthly rental for these {phoneNumbers.length} line
        {phoneNumbers.length === 1 ? '' : 's'}:{' '}
        <span className="font-mono font-semibold text-[#0F0E17]">
          ${monthlyRentalUsd.toFixed(2)}
        </span>{' '}
        per month. Call time is billed separately from your wallet.
      </div>

      {/* Numbers Inventory Table Card */}
      <SolidCard padding="p-0" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                <th className="py-3 px-5">Phone Number</th>
                <th className="py-3 px-4">Location / Type</th>
                <th className="py-3 px-4">Assigned AI Employee</th>
                <th className="py-3 px-4 font-mono">Monthly Rate</th>
                <th className="py-3 px-4">Calls</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4E2EB]">
              {phoneNumbers.map((num) => (
                <tr key={num.id} className="hover:bg-[#FAF9FD] transition-colors">
                  {/* Number & Capabilities */}
                  <td className="py-4 px-5">
                    <div className="font-mono font-bold text-sm text-[#0F0E17] flex items-center gap-2 flex-wrap">
                      <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
                      <span>{num.number}</span>
                      {num.isDevSandbox && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-200">
                          {num.label || 'Shared test line'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {num.capabilities?.map((cap) => (
                        <span key={cap} className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]">
                          {cap}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Locality */}
                  <td className="py-4 px-4">
                    <div className="font-semibold text-[#0F0E17]">{num.locality}</div>
                    <div className="text-[11px] text-[#524E5E]">{num.country} • {num.type}</div>
                  </td>

                  {/* Assigned Agent Dropdown */}
                  <td className="py-4 px-4">
                    <select
                      value={num.assignedAgentId || ''}
                      onChange={async (e) => {
                        try {
                          await assignNumberToAgent(num.id, e.target.value);
                          showToast(e.target.value ? 'Number assigned' : 'Number unassigned', 'success');
                        } catch (err) {
                          showToast(err.message || 'Could not assign number', 'error');
                        }
                      }}
                      className="bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#D1CFDB] rounded-xl px-2.5 py-1.5 text-xs text-[#0F0E17] font-medium focus:outline-none focus:border-[#6344E7] transition-colors"
                    >
                      <option value="">Unassigned (Pool)</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name} ({agent.role})
                        </option>
                      ))}
                    </select>
                  </td>

                  {/* Monthly Cost */}
                  <td className="py-4 px-4 font-mono text-[#524E5E]">
                    ${Number(num.monthlyCost || 0).toFixed(2)}/mo
                  </td>

                  {/* Line-level inbound/outbound switches */}
                  <td className="py-4 px-4">
                    <div className="flex flex-col gap-1">
                      <label className="flex items-center gap-1.5 text-[10px] text-[#524E5E]">
                        <input
                          type="checkbox"
                          checked={num.inboundEnabled !== false}
                          onChange={async (e) => {
                            try {
                              await updateNumberRouting(num.id, {
                                inboundEnabled: e.target.checked,
                              });
                            } catch (err) {
                              showToast(err.message || 'Could not update', 'error');
                            }
                          }}
                          data-testid={`number-inbound-${num.id}`}
                          className="w-3 h-3 accent-[#6344E7]"
                        />
                        Accepts calls
                      </label>
                      <label className="flex items-center gap-1.5 text-[10px] text-[#524E5E]">
                        <input
                          type="checkbox"
                          checked={num.outboundEnabled !== false}
                          onChange={async (e) => {
                            try {
                              await updateNumberRouting(num.id, {
                                outboundEnabled: e.target.checked,
                              });
                            } catch (err) {
                              showToast(err.message || 'Could not update', 'error');
                            }
                          }}
                          data-testid={`number-outbound-${num.id}`}
                          className="w-3 h-3 accent-[#6344E7]"
                        />
                        Can call out
                      </label>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-4 px-4">
                    <StatusBadge status={num.status} size="xs" />
                  </td>

                  {/* Actions */}
                  <td className="py-4 px-5 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm(`Release ${num.number}? It will be returned to the carrier pool.`)) {
                          releasePhoneNumber(num.id);
                        }
                      }}
                      className="text-xs font-semibold text-[#DC2626] hover:underline"
                    >
                      Release
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SolidCard>

      {/* BUY VIRTUAL NUMBER MODAL */}
      <Modal
        isOpen={isBuyModalOpen}
        onClose={onCloseBuyModal}
        title={
          purchasedSuccess
            ? 'Number ready'
            : !kycApproved
              ? 'Verify identity'
              : 'Buy Virtual Telephone Number'
        }
        subtitle={
          purchasedSuccess
            ? undefined
            : !kycApproved
              ? 'One quick ID check unlocks phone numbers and live calls.'
              : 'Only numbers currently available in your selected country are shown.'
        }
        maxWidth="max-w-2xl"
      >
        <div className="space-y-5">
          {purchasedSuccess ? (
            <div className="p-8 text-center space-y-2">
              <CheckCircle2 className="w-10 h-10 text-[#047857] mx-auto animate-bounce" />
              <h3 className="text-base font-bold text-[#0F0E17]">Number Successfully Provisioned!</h3>
              <p className="font-mono text-sm text-[#6344E7]">{purchasedSuccess}</p>
              <p className="text-xs text-[#524E5E]">Inbound calls will now route directly to your selected AI agent.</p>
            </div>
          ) : !kycApproved ? (
            <VerifyIdentityCard
              variant="gate"
              onApproved={() => {
                setKycApproved(true);
              }}
            />
          ) : (
            <>
              {buyError && (
                <div
                  data-testid="buy-number-error"
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900 flex items-start gap-2"
                >
                  <p className="flex-1">{buyError}</p>
                  <button
                    type="button"
                    aria-label="Dismiss"
                    className="shrink-0 p-1 rounded-md hover:bg-red-100"
                    onClick={() => setBuyError(null)}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Price and affordability, both from the server. USD only. */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <div className="text-[11px] text-[#524E5E]">
                  <span className="font-semibold text-[#0F0E17]">
                    {priceKnown ? `$${numberPriceUsd.toFixed(2)}` : 'Loading price…'} / month
                  </span>
                  {', charged to your wallet when you buy.'}
                  <span className="block mt-0.5 text-[10px] text-[#8C879A]">
                    Same rate on every number below — monthly rental.
                  </span>
                  <span className="block mt-0.0">
                    Wallet: ${balanceUsd.toFixed(2)}
                  </span>
                </div>
                {priceKnown && !canAffordNumber && (
                  <button
                    type="button"
                    className="shrink-0 text-[11px] font-semibold text-[#B45309] hover:underline"
                    onClick={() => openAddFunds?.('buy-number')}
                  >
                    Add credit to buy a number
                  </button>
                )}
              </div>

              {/* Search Filters */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                {/* Country */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Country</label>
                  <select
                    value={selectedCountry}
                    onChange={(e) => setSelectedCountry(e.target.value)}
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                    data-testid="buy-number-country"
                  >
                    {countries.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name} ({c.dial})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Type */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Number Type</label>
                  <select
                    value={selectedType}
                    onChange={(e) => setSelectedType(e.target.value)}
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                  >
                    <option value="Local DID">Local DID (Area Code)</option>
                    <option value="Toll-Free">Toll-Free (800 / 888)</option>
                    <option value="All">All Types</option>
                  </select>
                </div>

                {/* Area Code */}
                <div>
                  <label className="block text-[10px] font-bold text-[#8C879A] uppercase mb-1">Area Code / Prefix</label>
                  <input
                    type="text"
                    value={searchAreaCode}
                    onChange={(e) => setSearchAreaCode(e.target.value)}
                    placeholder="e.g. 415, 212, 800"
                    className="w-full bg-white border border-[#E4E2EB] rounded-lg p-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                  />
                </div>
              </div>

              {/* Direct Agent Binding Dropdown */}
              <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-bold text-[#0F0E17] block">Assign Directly to AI Employee</span>
                  <span className="text-[11px] text-[#524E5E]">Optional: Route all inbound traffic immediately to this agent.</span>
                </div>
                <select
                  value={targetAgentId}
                  onChange={(e) => setTargetAgentId(e.target.value)}
                  className="bg-white border border-[#E4E2EB] rounded-xl px-3 py-1.5 text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  <option value="">Leave Unassigned (Pool)</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.role})
                    </option>
                  ))}
                </select>
              </div>

              {/* Available Inventory Results */}
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {catalogLoading ? (
                  <CatalogSkeleton rows={4} />
                ) : catalogError ? (
                  <div className="p-6 text-center text-xs text-red-800 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2">
                    <p className="flex-1">{catalogError}</p>
                    <button type="button" aria-label="Dismiss" onClick={() => setCatalogError(null)}>
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : filteredCatalog.length === 0 ? (
                  <div className="p-8 text-center text-xs text-[#524E5E]">
                    No phone numbers are available for <strong>{selectedCountry}</strong> right
                    now. Try another country or check back later.
                  </div>
                ) : (
                  filteredCatalog.map((item) => (
                    <div
                      key={item.formatted || item.number || item.e164}
                      className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] hover:border-[#D1CFDB] flex items-center justify-between gap-4 transition-all shadow-2xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7]">
                          <Phone className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="font-mono font-bold text-sm text-[#0F0E17]">{item.number}</div>
                          <div className="text-[10px] text-[#524E5E]">{item.locality} • {item.type}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-semibold text-[#524E5E]">
                          ${Number(
                            numberPriceUsd || item.monthlyUsd || item.fee || 0
                          ).toFixed(2)}/mo
                          {item.source === 'inventory' ? (
                            <span className="ml-1 text-[10px] text-[#047857]">In stock</span>
                          ) : null}
                        </span>
                        <TactileButton
                          size="xs"
                          variant="primary"
                          disabled={buying || (priceKnown && !canAffordNumber)}
                          loading={buying}
                          onClick={() => handleBuyNumber(item)}
                          data-testid="buy-number-submit"
                        >
                          {buying ? 'Buying…' : 'Buy & Bind'}
                        </TactileButton>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
