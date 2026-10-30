import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Loader2, PhoneCall } from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { showToast } from '../ui/ToastHost';

/**
 * Concurrent call channels: how many calls can run at once, buying or reducing
 * paid channels (with the exact charge shown before confirming), and usage
 * analytics (peak in use, calls refused or queued for lack of a channel, and
 * channel charges over time).
 */

const EVENT_LABEL = {
  purchase: 'Channels purchased',
  renewal: '30-day renewal',
  renewal_failed: 'Renewal failed (grace period)',
  lapsed: 'Paid channels ended',
  downgrade_scheduled: 'Reduction scheduled',
  downgrade_cancelled: 'Reduction cancelled',
  downgrade_applied: 'Paid channels ended at renewal',
};

function inr(value) {
  const amount = Number(value) || 0;
  return `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function shortDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function newRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Peak-in-use bars against the channel cap, one per day. */
function DailyBars({ daily }) {
  const max = Math.max(1, ...daily.map((d) => Math.max(d.peakActive, d.channelCap)));
  return (
    <div>
      <div className="flex items-end gap-[3px] h-24" role="img" aria-label="Peak simultaneous calls per day">
        {daily.map((d) => {
          const pressure = d.rejected + d.queued > 0;
          return (
            <div key={d.day} className="relative flex-1 h-full flex items-end" title={`${d.day}: peak ${d.peakActive} of ${d.channelCap} channels · ${d.rejected} refused · ${d.queued} queued`}>
              <div
                className="absolute left-0 right-0 border-t border-dashed border-[#B9B4C8]"
                style={{ bottom: `${(d.channelCap / max) * 100}%` }}
              />
              <div
                className={`w-full rounded-t-sm ${pressure ? 'bg-[#D97706]' : 'bg-[#6344E7]'}`}
                style={{ height: `${(d.peakActive / max) * 100}%`, minHeight: d.peakActive ? 2 : 0 }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[#8A8698]">
        <span>{daily[0]?.day}</span>
        <span>{daily[daily.length - 1]?.day}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-[#524E5E]">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-[#6344E7]" /> Peak calls at once</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-[#D97706]" /> Day with refused or queued calls</span>
        <span className="flex items-center gap-1"><span className="w-3 border-t border-dashed border-[#B9B4C8]" /> Channel limit</span>
      </div>
    </div>
  );
}

export function ChannelsPanel({ onCharged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState(0);
  const [quote, setQuote] = useState(null);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const requestIdRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const view = await api.request('GET', '/api/billing/channels?days=30');
      setData(view);
      const paid = view?.subscription?.pendingPaidChannels ?? view?.channels?.paid ?? 0;
      setTarget(paid);
      setError(null);
    } catch (err) {
      setError(err?.message || 'Channel details could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pricing = data?.pricing;
  const offered = Boolean(pricing?.configured);
  const currentPaid = data?.channels?.paid ?? 0;
  const pending = data?.subscription?.pendingPaidChannels;
  const changed = offered && (target !== currentPaid || (pending != null && target === currentPaid));

  const requestQuote = useCallback(async () => {
    setQuoteBusy(true);
    try {
      const q = await api.request('POST', '/api/billing/channels/quote', { paidChannels: target });
      setQuote(q);
      requestIdRef.current = newRequestId();
      setConfirming(true);
    } catch (err) {
      showToast(err?.message || 'Could not price this change.', 'error');
    } finally {
      setQuoteBusy(false);
    }
  }, [target]);

  const confirm = useCallback(async () => {
    if (!quote || busy) return;
    setBusy(true);
    try {
      const result = await api.request('POST', '/api/billing/channels', {
        paidChannels: quote.targetPaidChannels,
        requestId: requestIdRef.current,
        expectedChargeInrPaise: quote.chargeNowInrPaise,
      });
      const charged = Number(result?.chargedInrPaise || 0) / 100;
      showToast(
        result?.kind === 'downgrade_scheduled'
          ? 'Reduction scheduled for your next renewal.'
          : charged > 0
            ? `Channels updated. ${inr(charged)} was charged to your wallet.`
            : 'Channels updated.',
        'success'
      );
      setConfirming(false);
      setQuote(null);
      await load();
      onCharged?.();
    } catch (err) {
      if (err?.code === 'quote_changed') {
        showToast('The price changed. Review the new total.', 'error');
        setConfirming(false);
        await requestQuote();
      } else {
        showToast(err?.message || 'Channels could not be changed.', 'error');
      }
    } finally {
      setBusy(false);
    }
  }, [quote, busy, load, onCharged, requestQuote]);

  const totals = data?.totals;
  const daily = useMemo(() => data?.daily || [], [data]);

  if (loading) {
    return (
      <SolidCard className="flex items-center gap-2 text-xs text-[#524E5E]">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading call channels…
      </SolidCard>
    );
  }
  if (error) {
    return (
      <SolidCard className="flex items-center justify-between gap-3 text-xs text-[#B42318]">
        <span className="flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</span>
        <TactileButton variant="secondary" size="xs" onClick={load}>Retry</TactileButton>
      </SolidCard>
    );
  }

  const ch = data?.channels || {};
  const sub = data?.subscription;

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="channels-panel">
      <SolidCard className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-1.5">
              <PhoneCall className="w-3.5 h-3.5" /> Call channels
            </h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              A channel is one phone call running at the same time. Extra inbound calls are refused and
              campaign calls wait in the queue until a channel frees up.
            </p>
          </div>
          <div className="text-right shrink-0">
            <div className="text-xl font-bold text-[#0F0E17] font-mono">{ch.activeNow ?? 0}/{ch.cap ?? 0}</div>
            <div className="text-[10px] text-[#8A8698]">in use now</div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2">
            <div className="font-mono font-bold">{ch.included ?? 0}</div>
            <div className="text-[10px] text-[#524E5E]">Included</div>
          </div>
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2">
            <div className="font-mono font-bold">{ch.paid ?? 0}</div>
            <div className="text-[10px] text-[#524E5E]">Paid</div>
          </div>
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2">
            <div className="font-mono font-bold">{ch.cap ?? 0}</div>
            <div className="text-[10px] text-[#524E5E]">Total limit</div>
          </div>
        </div>

        {sub?.notice && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-[11px] text-amber-900 flex gap-2" role="status">
            <AlertCircle className="w-4 h-4 shrink-0" /> <span>{sub.notice}</span>
          </div>
        )}

        {!offered ? (
          <p className="text-[11px] text-[#524E5E]">Additional channels are not offered on this platform yet.</p>
        ) : (
          <>
            <p className="text-[11px] text-[#524E5E]">
              {pricing.free
                ? 'Extra channels are currently free.'
                : <>Extra channels cost <strong className="text-[#0F0E17]">{inr(pricing.priceInrPerChannel)}</strong> each per {pricing.periodDays} days, paid from your wallet.</>}
              {sub?.periodEnd && sub.status !== 'lapsed' ? ` Next renewal: ${shortDate(sub.periodEnd)}.` : ''}
              {pending != null ? ` Reducing to ${pending} paid at renewal.` : ''}
            </p>
            <div className="flex items-center gap-2">
              <label htmlFor="paid-channels" className="text-xs text-[#524E5E]">Paid channels</label>
              <TactileButton variant="secondary" size="xs" aria-label="Fewer channels" disabled={target <= 0} onClick={() => setTarget((t) => Math.max(0, t - 1))}>−</TactileButton>
              <input
                id="paid-channels"
                type="number"
                min="0"
                max={pricing.maxChannelsPerTenant || pricing.platformCapacity || 10000}
                value={target}
                onChange={(e) => setTarget(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
                className="w-20 min-h-[36px] rounded-xl border border-[#E4E2EB] bg-white px-2 text-center text-xs font-mono focus:outline-none focus:border-[#6344E7]"
              />
              <TactileButton variant="secondary" size="xs" aria-label="More channels" onClick={() => setTarget((t) => t + 1)}>+</TactileButton>
              <TactileButton size="sm" className="ml-auto" disabled={!changed} loading={quoteBusy} onClick={requestQuote}>
                Review change
              </TactileButton>
            </div>

            {confirming && quote && (
              <div className="rounded-xl border border-[#6344E7]/40 bg-[#F5F2FF] p-3 space-y-2 text-xs" data-testid="channels-quote">
                <div className="flex justify-between"><span>Paid channels</span><span className="font-mono">{quote.currentPaidChannels} → {quote.targetPaidChannels}</span></div>
                <div className="flex justify-between"><span>Total channels after</span><span className="font-mono">{quote.totalChannelsAfter}</span></div>
                {quote.rule === 'downgrade_at_period_end' ? (
                  <p className="text-[11px] text-[#524E5E]">
                    Nothing is charged or refunded now. You keep {quote.currentPaidChannels} paid channels until {shortDate(quote.periodEnd)}; the renewal then charges for {quote.targetPaidChannels}.
                  </p>
                ) : quote.rule === 'cancel_pending_downgrade' ? (
                  <p className="text-[11px] text-[#524E5E]">Cancels the scheduled reduction. Nothing is charged now.</p>
                ) : (
                  <>
                    <div className="flex justify-between font-bold">
                      <span>Charged now</span>
                      <span className="font-mono">{inr(quote.chargeNowInr)}</span>
                    </div>
                    <p className="text-[11px] text-[#524E5E]">
                      {quote.free
                        ? 'Channels are free right now; nothing is debited.'
                        : quote.rule === 'prorated'
                          ? `${inr(quote.priceInrPerChannel)} × ${quote.targetPaidChannels - quote.currentPaidChannels} added channel(s), prorated to your renewal on ${shortDate(quote.periodEnd)}.`
                          : `${inr(quote.priceInrPerChannel)} × ${quote.targetPaidChannels} channel(s) for ${quote.periodDays} days, until ${shortDate(quote.periodEnd)}.`}
                      {!quote.free && ` Renews at ${inr(quote.recurringInr)} every ${quote.periodDays} days from your wallet credit (GST was invoiced on your top-up).`}
                    </p>
                  </>
                )}
                <div className="flex justify-end gap-2 pt-1">
                  <TactileButton variant="secondary" size="sm" onClick={() => { setConfirming(false); setQuote(null); }}>Cancel</TactileButton>
                  <TactileButton size="sm" loading={busy} onClick={confirm}>
                    {quote.chargeNowInrPaise > 0 ? `Confirm and pay ${inr(quote.chargeNowInr)}` : 'Confirm'}
                  </TactileButton>
                </div>
              </div>
            )}
          </>
        )}
      </SolidCard>

      <SolidCard className="space-y-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F0E17]">Channel usage · last 30 days</h3>
          <p className="text-[11px] text-[#524E5E] mt-0.5">Peak simultaneous calls each day against your limit.</p>
        </div>
        <div className="grid grid-cols-4 gap-2 text-center text-xs">
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2"><div className="font-mono font-bold">{totals?.peakActive ?? 0}</div><div className="text-[10px] text-[#524E5E]">Peak at once</div></div>
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2"><div className="font-mono font-bold">{totals?.admitted ?? 0}</div><div className="text-[10px] text-[#524E5E]">Calls connected</div></div>
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2"><div className="font-mono font-bold">{totals?.rejected ?? 0}</div><div className="text-[10px] text-[#524E5E]">Refused (busy)</div></div>
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-2"><div className="font-mono font-bold">{totals?.queued ?? 0}</div><div className="text-[10px] text-[#524E5E]">Campaign waits</div></div>
        </div>
        {daily.length > 0 && <DailyBars daily={daily} />}
        {(totals?.rejected || 0) + (totals?.queued || 0) > 0 && offered && (
          <p className="text-[11px] text-amber-800">
            Calls were refused or queued because every channel was busy. Adding channels lets more calls run at once.
          </p>
        )}
        <div className="pt-2 border-t border-[#E4E2EB]">
          <h4 className="text-[11px] font-bold text-[#0F0E17] mb-1">Channel charges and changes</h4>
          {(data?.events || []).length === 0 ? (
            <p className="text-[11px] text-[#8A8698]">No channel changes yet.</p>
          ) : (
            <ul className="space-y-1 max-h-40 overflow-y-auto text-[11px]">
              {data.events.map((ev) => (
                <li key={ev.id} className="flex justify-between gap-2">
                  <span className="text-[#524E5E]">
                    {shortDate(ev.createdAt)} · {EVENT_LABEL[ev.kind] || ev.kind} ({ev.channelsBefore} → {ev.channelsAfter})
                  </span>
                  <span className="font-mono text-[#0F0E17]">{ev.amountInr > 0 ? `−${inr(ev.amountInr)}` : ev.amountUsd > 0 ? `−$${ev.amountUsd.toFixed(2)}` : '—'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </SolidCard>
    </div>
  );
}
