import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Link2 } from 'lucide-react';
import { formatInrAmount, pricedTiers } from '../lib/usePricingCatalog';
import '../styles/usage-calculator.css';

const CALL_PRESETS = [100, 500, 2000];
const MINUTE_PRESETS = [200, 800, 2000];
const MAX_CALLS = 5000;
const MAX_MONTHLY_MINUTES = 10000;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function minutesLabel(value) {
  return Number.isInteger(value) ? `${value} min` : `${value.toFixed(1)} min`;
}

function finiteRate(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function parseShareParams() {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const shared = {};
  const mode = params.get('mode');
  if (mode === 'calls' || mode === 'minutes') shared.mode = mode;
  const tier = params.get('tier');
  if (tier) shared.tier = tier;
  const calls = params.get('calls');
  if (calls !== null && Number.isFinite(Number(calls))) {
    shared.calls = clamp(Math.round(Number(calls)), 0, MAX_CALLS);
  }
  const length = params.get('len');
  if (length !== null && Number.isFinite(Number(length))) {
    shared.minutes = clamp(Number(length), 0.5, 15);
  }
  const monthly = params.get('mins');
  if (monthly !== null && Number.isFinite(Number(monthly))) {
    shared.monthlyMinutes = clamp(Math.round(Number(monthly)), 0, MAX_MONTHLY_MINUTES);
  }
  const gst = params.get('gst');
  if (gst === 'incl' || gst === 'ex') shared.gstView = gst;
  return shared;
}

export function UsageCalculator({ catalog, loading, error, onRetry, onSelectPlan, syncUrl = false }) {
  const tiers = pricedTiers(catalog);
  const [tierId, setTierId] = useState('');
  const [mode, setMode] = useState('calls');
  const [calls, setCalls] = useState(500);
  const [minutes, setMinutes] = useState(3);
  const [monthlyMinutes, setMonthlyMinutes] = useState(1500);
  const [gstView, setGstView] = useState(null);
  const [shareStatus, setShareStatus] = useState('idle');
  const [manualUrl, setManualUrl] = useState('');
  const [shareReady, setShareReady] = useState(!syncUrl);
  const hydratedShare = useRef(false);

  const flags = catalog?.calculator || {};
  const allowMinuteInput = flags.allowMinuteInput !== false;
  const compareTiers = flags.compareTiers !== false;
  const shareableEstimate = flags.shareableEstimate !== false;
  const showGstToggle = flags.showGstToggle !== false;

  const volumeMode = allowMinuteInput && mode === 'minutes' ? 'minutes' : 'calls';
  const totalMinutes = volumeMode === 'minutes' ? monthlyMinutes : calls * minutes;
  const effectiveCalls = volumeMode === 'minutes'
    ? (minutes > 0 ? Math.round(totalMinutes / minutes) : 0)
    : Math.round(calls);

  const activeTier = tiers.find((tier) => tier.id === tierId) || tiers[0] || null;
  const phoneRate = finiteRate(activeTier?.pstn?.inrPerMin);
  const gstRate = finiteRate(catalog?.tax?.ratePercent) ?? 0;
  const gstConfigured = catalog?.tax?.enabled === true && gstRate > 0;
  const gstViewEnabled = showGstToggle && gstConfigured;
  // When shelf prices already include tax, the published rate is the gross rate,
  // so the default view matches the price shown on the pricing cards.
  const priceIncludesTax = gstConfigured && catalog?.tax?.priceIncludesTax === true;
  const publishedTaxView = priceIncludesTax ? 'incl' : 'ex';
  const taxView = gstViewEnabled ? (gstView ?? publishedTaxView) : publishedTaxView;
  const taxMultiplier = 1 + gstRate / 100;
  const exFactor = priceIncludesTax ? 1 / taxMultiplier : 1;

  const rateFor = (rate) => {
    const ex = rate * exFactor;
    return taxView === 'incl' ? ex * taxMultiplier : ex;
  };

  const subtotalEx = phoneRate != null ? totalMinutes * phoneRate * exFactor : null;
  const gstAmount = subtotalEx != null ? (subtotalEx * gstRate) / 100 : null;
  const inclTotal = subtotalEx != null ? subtotalEx + gstAmount : null;
  const total = subtotalEx != null ? (taxView === 'incl' ? inclTotal : subtotalEx) : null;
  const displayRate = phoneRate != null ? rateFor(phoneRate) : null;
  const perCall = total != null && effectiveCalls > 0 ? total / effectiveCalls : null;
  const showTaxControls = gstViewEnabled && phoneRate != null;

  useEffect(() => {
    if (!syncUrl || hydratedShare.current) return;
    hydratedShare.current = true;
    const shared = parseShareParams();
    if (shared) {
      if (shared.tier) setTierId(shared.tier);
      if (shared.mode) setMode(shared.mode);
      if (shared.calls != null) setCalls(shared.calls);
      if (shared.minutes != null) setMinutes(shared.minutes);
      if (shared.monthlyMinutes != null) setMonthlyMinutes(shared.monthlyMinutes);
      if (shared.gstView) setGstView(shared.gstView);
    }
    setShareReady(true);
  }, [syncUrl]);

  useEffect(() => {
    if (!syncUrl || !shareReady || !shareableEstimate || !catalog || typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    if (activeTier) params.set('tier', activeTier.id);
    else params.delete('tier');
    params.set('mode', volumeMode);
    params.set('calls', String(calls));
    params.set('len', String(minutes));
    params.set('mins', String(monthlyMinutes));
    if (gstViewEnabled) params.set('gst', taxView);
    else params.delete('gst');
    const query = params.toString();
    try {
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`
      );
    } catch {
      // Embedded previews can block history updates; the estimate still works without a URL.
    }
  }, [
    syncUrl,
    shareReady,
    shareableEstimate,
    catalog,
    activeTier?.id,
    volumeMode,
    calls,
    minutes,
    monthlyMinutes,
    gstViewEnabled,
    taxView,
  ]);

  useEffect(() => {
    setShareStatus('idle');
  }, [activeTier?.id, volumeMode, calls, minutes, monthlyMinutes, taxView]);

  if (loading && !catalog) {
    return (
      <div className="usage-calculator is-loading" aria-busy="true" aria-label="Loading usage calculator">
        <div className="usage-skeleton" />
        <div className="usage-skeleton usage-skeleton--result" />
      </div>
    );
  }

  if (error && !catalog) {
    return (
      <div className="usage-calculator is-error" role="status">
        <div>
          <h3>The calculator could not load current rates.</h3>
          <p>Prices are always shown in your workspace before a call is placed.</p>
        </div>
        <button type="button" className="usage-secondary-button" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }

  function changeMode(next) {
    if (next === volumeMode) return;
    if (next === 'minutes') {
      setMonthlyMinutes(clamp(Math.round(calls * minutes), 0, MAX_MONTHLY_MINUTES));
    } else {
      setCalls(
        minutes > 0 ? clamp(Math.round(totalMinutes / minutes), 0, MAX_CALLS) : 0
      );
    }
    setMode(next);
  }

  function buildShareUrl() {
    const params = new URLSearchParams();
    if (activeTier) params.set('tier', activeTier.id);
    else params.delete('tier');
    params.set('mode', volumeMode);
    params.set('calls', String(calls));
    params.set('len', String(minutes));
    params.set('mins', String(monthlyMinutes));
    if (gstViewEnabled) params.set('gst', taxView);
    else params.delete('gst');
    return `${window.location.origin}/pricing?${params.toString()}`;
  }

  async function copyShareLink() {
    const url = buildShareUrl();
    setManualUrl(url);
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard_unavailable');
      await navigator.clipboard.writeText(url);
      setShareStatus('copied');
    } catch {
      setShareStatus('error');
    }
  }

  return (
    <div className="usage-calculator-shell">
      <div className="usage-calculator" data-testid="usage-calculator">
        <div className="usage-form">
          <div className="usage-field">
            <label htmlFor="usage-tier">Voice tier</label>
            <select
              id="usage-tier"
              value={activeTier?.id || ''}
              onChange={(event) => setTierId(event.target.value)}
              disabled={!tiers.length}
            >
              {tiers.map((tier) => (
                <option key={tier.id} value={tier.id}>{tier.label}</option>
              ))}
            </select>
            {activeTier ? (
              <p className="usage-tier-rate" data-testid="usage-tier-rate">
                {phoneRate != null ? (
                  <>
                    <strong>{formatInrAmount(phoneRate)}</strong> per phone minute
                  </>
                ) : (
                  'Per-minute rate shown in your workspace'
                )}
              </p>
            ) : null}
            {activeTier?.tags?.length ? (
              <ul className="usage-tier-tags" aria-label={`${activeTier.label} highlights`}>
                {activeTier.tags.map((tag) => (
                  <li key={`${tag.label}-${tag.tone}`} data-tone={tag.tone || 'neutral'}>{tag.label}</li>
                ))}
              </ul>
            ) : null}
          </div>

          {allowMinuteInput ? (
            <div className="usage-mode" role="group" aria-label="How to enter your volume">
              <button
                type="button"
                aria-pressed={volumeMode === 'calls'}
                data-testid="usage-mode-calls"
                onClick={() => changeMode('calls')}
              >
                By calls
              </button>
              <button
                type="button"
                aria-pressed={volumeMode === 'minutes'}
                data-testid="usage-mode-minutes"
                onClick={() => changeMode('minutes')}
              >
                By minutes
              </button>
            </div>
          ) : null}

          {volumeMode === 'minutes' ? (
            <div className="usage-control">
              <div className="usage-control-head">
                <label htmlFor="usage-monthly-minutes">Talk time per month</label>
                <output htmlFor="usage-monthly-minutes">
                  {monthlyMinutes.toLocaleString('en-IN')} min
                </output>
              </div>
              <input
                id="usage-monthly-minutes"
                type="range"
                min="0"
                max={MAX_MONTHLY_MINUTES}
                step="50"
                value={monthlyMinutes}
                onChange={(event) => setMonthlyMinutes(Number(event.target.value))}
              />
              <div className="usage-presets" role="group" aria-label="Common monthly talk time">
                {MINUTE_PRESETS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    aria-pressed={monthlyMinutes === preset}
                    onClick={() => setMonthlyMinutes(preset)}
                  >
                    {preset.toLocaleString('en-IN')}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="usage-control">
              <div className="usage-control-head">
                <label htmlFor="usage-calls">Calls per month</label>
                <output htmlFor="usage-calls">{calls.toLocaleString('en-IN')}</output>
              </div>
              <input
                id="usage-calls"
                type="range"
                min="0"
                max={MAX_CALLS}
                step="50"
                value={calls}
                onChange={(event) => setCalls(Number(event.target.value))}
              />
              <div className="usage-presets" role="group" aria-label="Common call volumes">
                {CALL_PRESETS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    aria-pressed={calls === preset}
                    onClick={() => setCalls(preset)}
                  >
                    {preset.toLocaleString('en-IN')}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="usage-control">
            <div className="usage-control-head">
              <label htmlFor="usage-minutes">Average call length</label>
              <output htmlFor="usage-minutes">{minutesLabel(minutes)}</output>
            </div>
            <input
              id="usage-minutes"
              type="range"
              min="0.5"
              max="15"
              step="0.5"
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
            />
            <p className="usage-hint" data-testid="usage-talk-time">
              {volumeMode === 'minutes' ? (
                <>
                  At {minutesLabel(minutes)} per call, {minutesLabel(totalMinutes)} is about{' '}
                  <strong>{effectiveCalls.toLocaleString('en-IN')}</strong> calls
                </>
              ) : (
                <>
                  {calls.toLocaleString('en-IN')} calls × {minutesLabel(minutes)} ={' '}
                  <strong>{minutesLabel(totalMinutes)}</strong> of talk time
                </>
              )}
            </p>
          </div>

          <p className="usage-hint">
            Estimates use the published per-minute phone rate
            {gstConfigured ? ' and the published tax setting' : ' and exclude GST'}. Phone number
            rentals bill separately at their published monthly rate.
          </p>
        </div>

        <div className="usage-result" aria-live="polite">
          <div className="usage-result-head">
            <p className="usage-result-label">Estimated monthly call cost</p>
            {showTaxControls ? (
              <div className="usage-gst-toggle" role="group" aria-label="Tax view">
                <button
                  type="button"
                  aria-pressed={taxView === 'ex'}
                  data-testid="usage-gst-ex"
                  onClick={() => setGstView('ex')}
                >
                  {formatInrAmount(subtotalEx)}
                  <span>ex-GST</span>
                </button>
                <button
                  type="button"
                  aria-pressed={taxView === 'incl'}
                  data-testid="usage-gst-incl"
                  onClick={() => setGstView('incl')}
                >
                  {formatInrAmount(inclTotal)}
                  <span>incl. {gstRate}% GST</span>
                </button>
              </div>
            ) : null}
          </div>
          {phoneRate == null ? (
            <p className="usage-unavailable" data-testid="usage-estimate-unavailable">
              {activeTier
                ? 'A published per-minute rate for this tier is not available. Choose another tier or review the rates in your workspace.'
                : 'No voice tier is published right now. Review pricing in your workspace.'}
            </p>
          ) : (
            <>
              <p className="usage-total" data-testid="usage-estimate-total">{formatInrAmount(total)}</p>
              <p className="usage-total-formula" data-testid="usage-estimate-formula">
                {minutesLabel(totalMinutes)} × {formatInrAmount(displayRate)}/min
                {taxView === 'incl' && gstConfigured ? ` incl. ${gstRate}% GST` : ''}
              </p>
              <dl className="usage-breakdown">
                <div>
                  <dt>
                    Talk time
                    <span>{effectiveCalls.toLocaleString('en-IN')} calls × {minutesLabel(minutes)}</span>
                  </dt>
                  <dd>{minutesLabel(totalMinutes)}</dd>
                </div>
                <div>
                  <dt>
                    Phone agent rate
                    <span>
                      {activeTier.label} ·{' '}
                      {gstConfigured
                        ? taxView === 'incl'
                          ? `incl. ${gstRate}% GST`
                          : 'ex-GST'
                        : 'published per-minute rate'}
                    </span>
                  </dt>
                  <dd>{formatInrAmount(displayRate)}/min</dd>
                </div>
                {gstViewEnabled ? (
                  <>
                    <div>
                      <dt>
                        Subtotal
                        <span>before {gstRate}% GST</span>
                      </dt>
                      <dd>{formatInrAmount(subtotalEx)}</dd>
                    </div>
                    <div>
                      <dt>GST @ {gstRate}%</dt>
                      <dd>{formatInrAmount(gstAmount)}</dd>
                    </div>
                  </>
                ) : null}
                <div className="usage-breakdown-total">
                  <dt>
                    Average cost per call
                    <span>
                      {total != null && effectiveCalls > 0
                        ? `${formatInrAmount(total)} ÷ ${effectiveCalls.toLocaleString('en-IN')} calls`
                        : 'No calls at this volume'}
                    </span>
                  </dt>
                  <dd>{formatInrAmount(perCall)}</dd>
                </div>
              </dl>
            </>
          )}

          {shareableEstimate ? (
            <div className="usage-share" data-testid="usage-share">
              <button type="button" className="usage-share-button" onClick={copyShareLink}>
                <Link2 size={15} aria-hidden="true" />
                Copy estimate link
              </button>
              <p className="usage-share-status" role="status">
                {shareStatus === 'copied'
                  ? 'Link copied — it reopens this exact scenario.'
                  : shareStatus === 'error'
                    ? 'Copy failed. Select the link below instead.'
                    : 'Share this exact tier and volume.'}
              </p>
              {shareStatus === 'error' ? (
                <input
                  className="usage-share-input"
                  readOnly
                  value={manualUrl}
                  onFocus={(event) => event.target.select()}
                  aria-label="Estimate link"
                />
              ) : null}
            </div>
          ) : null}

          {onSelectPlan && (
            <button type="button" className="usage-result-action" onClick={onSelectPlan}>
              Open workspace pricing
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {compareTiers && tiers.length > 1 ? (
        <section className="usage-compare" aria-labelledby="usage-compare-heading" data-testid="usage-compare">
          <div className="usage-compare-head">
            <h3 id="usage-compare-heading">Same volume, every tier</h3>
            <p>{minutesLabel(totalMinutes)} per month at each published per-minute rate</p>
          </div>
          <ul className="usage-compare-grid">
            {tiers.map((tier) => {
              const tierRate = finiteRate(tier?.pstn?.inrPerMin);
              const tierTotal = tierRate != null ? totalMinutes * rateFor(tierRate) : null;
              return (
                <li key={tier.id} className="usage-compare-card" data-tier={tier.id}>
                  <span className="usage-compare-label">{tier.label}</span>
                  <span className="usage-compare-rate">
                    {tierRate != null ? `${formatInrAmount(tierRate)}/min` : 'Rate in workspace'}
                  </span>
                  <strong>{tierTotal != null ? formatInrAmount(tierTotal) : '—'}</strong>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
