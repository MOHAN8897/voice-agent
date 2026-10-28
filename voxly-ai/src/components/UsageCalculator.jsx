import React, { useState } from 'react';
import { ArrowLeftRight, ArrowRight, Minus, Monitor, Phone, Plus } from 'lucide-react';
import {
  catalogNumberMonthly,
  formatInrAmount,
  formatUsdAmount,
  pricedTiers,
} from '../lib/usePricingCatalog';
import '../styles/usage-calculator.css';

const CALL_PRESETS = [100, 500, 2000];
const CHANNELS = [
  { id: 'phone', label: 'Phone agent', icon: Phone },
  { id: 'web', label: 'Web agent', icon: Monitor },
  { id: 'mixed', label: 'Mixed', icon: ArrowLeftRight },
];

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function minutesLabel(value) {
  return Number.isInteger(value) ? `${value} min` : `${value.toFixed(1)} min`;
}

export function UsageCalculator({ catalog, loading, error, onRetry, onSelectPlan }) {
  const tiers = pricedTiers(catalog);
  const [tierId, setTierId] = useState('');
  const [calls, setCalls] = useState(500);
  const [minutes, setMinutes] = useState(3);
  const [channel, setChannel] = useState('phone');
  const [mixedShare, setMixedShare] = useState(60);
  const [numbers, setNumbers] = useState(1);

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

  const activeTier = tiers.find((tier) => tier.id === tierId) || tiers[0] || null;
  const numberMonthly = catalogNumberMonthly(catalog);
  const share = channel === 'phone' ? 100 : channel === 'web' ? 0 : mixedShare;

  const totalMinutes = calls * minutes;
  const phoneMinutes = totalMinutes * (share / 100);
  const webMinutes = totalMinutes - phoneMinutes;
  const phoneRate = activeTier?.pstn?.inrPerMin;
  const webRate = activeTier?.web?.inrPerMin;

  const missingPhone = phoneMinutes > 0 && !Number.isFinite(phoneRate);
  const missingWeb = webMinutes > 0 && !Number.isFinite(webRate);
  const missingNumbers = numbers > 0 && !Number.isFinite(numberMonthly.inr);
  const rateMissing = !activeTier || missingPhone || missingWeb || missingNumbers;

  const phoneCost = !rateMissing ? phoneMinutes * phoneRate : 0;
  const webCost = !rateMissing ? webMinutes * webRate : 0;
  const numbersCost = !rateMissing && numbers > 0 ? numbers * numberMonthly.inr : 0;
  const total = rateMissing ? null : phoneCost + webCost + numbersCost;
  const perCall = !rateMissing && calls > 0 ? (phoneCost + webCost) / calls : null;
  const fx = Number(catalog?.rates?.fxRateInr);
  const totalUsd = total != null && Number.isFinite(fx) && fx > 0 ? total / fx : null;

  return (
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
          {activeTier?.tags?.length ? (
            <ul className="usage-tier-tags" aria-label={`${activeTier.label} highlights`}>
              {activeTier.tags.map((tag) => (
                <li key={`${tag.label}-${tag.tone}`} data-tone={tag.tone || 'neutral'}>{tag.label}</li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="usage-control">
          <div className="usage-control-head">
            <label htmlFor="usage-calls">Calls per month</label>
            <output htmlFor="usage-calls">{calls.toLocaleString('en-IN')}</output>
          </div>
          <input
            id="usage-calls"
            type="range"
            min="0"
            max="5000"
            step="50"
            value={calls}
            onChange={(event) => setCalls(toNumber(event.target.value))}
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
            onChange={(event) => setMinutes(toNumber(event.target.value))}
          />
        </div>

        <fieldset className="usage-channel">
          <legend>Where the calls happen</legend>
          <div className="usage-channel-options">
            {CHANNELS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                aria-pressed={channel === id}
                onClick={() => setChannel(id)}
              >
                <Icon size={16} aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
          {channel === 'mixed' && (
            <div className="usage-control usage-control--inline">
              <div className="usage-control-head">
                <label htmlFor="usage-share">Phone / web split</label>
                <output htmlFor="usage-share">{share}% phone · {100 - share}% web</output>
              </div>
              <input
                id="usage-share"
                type="range"
                min="10"
                max="90"
                step="10"
                value={mixedShare}
                onChange={(event) => setMixedShare(toNumber(event.target.value))}
              />
            </div>
          )}
        </fieldset>

        <div className="usage-number-row">
          <div>
            <span className="usage-number-label">Phone numbers</span>
            <span className="usage-hint">
              {numberMonthly.inr != null
                ? `${formatInrAmount(numberMonthly.inr)}/month each`
                : 'Rental shown in your workspace'}
            </span>
          </div>
          <div className="usage-stepper">
            <button
              type="button"
              onClick={() => setNumbers((value) => clamp(value - 1, 0, 20))}
              disabled={numbers <= 0}
              aria-label="Remove a phone number"
            >
              <Minus size={15} aria-hidden="true" />
            </button>
            <output aria-live="polite">{numbers}</output>
            <button
              type="button"
              onClick={() => setNumbers((value) => clamp(value + 1, 0, 20))}
              disabled={numbers >= 20}
              aria-label="Add a phone number"
            >
              <Plus size={15} aria-hidden="true" />
            </button>
          </div>
        </div>

        <p className="usage-hint">
          Estimates use the current published rates and exclude GST. Checkout shows the applicable
          tax before payment.
        </p>
      </div>

      <div className="usage-result" aria-live="polite">
        <p className="usage-result-label">Estimated monthly total</p>
        {rateMissing ? (
          <p className="usage-unavailable" data-testid="usage-estimate-unavailable">
            {activeTier
              ? 'A published rate needed for this estimate is not available. Choose another tier or review the rates in your workspace.'
              : 'No voice tier is published right now. Review pricing in your workspace.'}
          </p>
        ) : (
          <>
            <p className="usage-total" data-testid="usage-estimate-total">{formatInrAmount(total)}</p>
            {totalUsd != null && (
              <p className="usage-total-usd">≈ {formatUsdAmount(totalUsd, 2)} at the configured exchange rate</p>
            )}
            <dl className="usage-breakdown">
              <div>
                <dt>
                  Phone agent
                  <span>
                    {phoneMinutes > 0
                      ? `${phoneMinutes.toFixed(1)} min · ${formatInrAmount(phoneRate)}/min`
                      : 'No phone minutes in this mix'}
                  </span>
                </dt>
                <dd>{formatInrAmount(phoneCost)}</dd>
              </div>
              <div>
                <dt>
                  Web agent
                  <span>
                    {webMinutes > 0
                      ? `${webMinutes.toFixed(1)} min · ${formatInrAmount(webRate)}/min`
                      : 'No web minutes in this mix'}
                  </span>
                </dt>
                <dd>{formatInrAmount(webCost)}</dd>
              </div>
              <div>
                <dt>
                  Phone numbers
                  <span>
                    {numbers > 0 ? `${numbers} × ${formatInrAmount(numberMonthly.inr)}` : 'None selected'}
                  </span>
                </dt>
                <dd>{formatInrAmount(numbersCost)}</dd>
              </div>
              <div className="usage-breakdown-total">
                <dt>
                  Average cost per call
                  <span>Phone and web minutes only</span>
                </dt>
                <dd>{formatInrAmount(perCall)}</dd>
              </div>
            </dl>
          </>
        )}
        {onSelectPlan && (
          <button type="button" className="usage-result-action" onClick={onSelectPlan}>
            Open workspace pricing
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
