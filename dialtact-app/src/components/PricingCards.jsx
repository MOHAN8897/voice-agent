import React from 'react';
import { ArrowRight } from 'lucide-react';
import {
  catalogNumberMonthly,
  formatInrAmount,
  formatUsdAmount,
  pricedTiers,
} from '../lib/usePricingCatalog';

function tiltMove(event) {
  if (typeof window === 'undefined' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width - 0.5;
  const y = (event.clientY - rect.top) / rect.height - 0.5;
  event.currentTarget.style.setProperty('--tilt-x', `${(-y * 4).toFixed(2)}deg`);
  event.currentTarget.style.setProperty('--tilt-y', `${(x * 5).toFixed(2)}deg`);
  event.currentTarget.style.setProperty('--glow-x', `${((x + 0.5) * 100).toFixed(1)}%`);
  event.currentTarget.style.setProperty('--glow-y', `${((y + 0.5) * 100).toFixed(1)}%`);
}

function tiltReset(event) {
  event.currentTarget.style.setProperty('--tilt-x', '0deg');
  event.currentTarget.style.setProperty('--tilt-y', '0deg');
}

function TierCard({ tier, index, numberMonthly, featuredStyle, onSelectPlan }) {
  const featured = tier.featured === true;
  const tags = Array.isArray(tier.tags) ? tier.tags : [];
  const pstn = tier.pstn;

  return (
    <div className="landing-price-reveal" style={{ '--card-index': index }}>
      <article
        className={`landing-price-card${featured ? ' is-featured' : ''}`}
        onPointerMove={tiltMove}
        onPointerLeave={tiltReset}
        data-tier={tier.id}
        data-featured={featured ? 'true' : 'false'}
        data-featured-style={featured ? featuredStyle : undefined}
      >
        <div className="landing-price-head">
          <h3 className="landing-price-label">{tier.label}</h3>
          {tags.length > 0 && (
            <ul className="landing-price-tags" aria-label={`${tier.label} highlights`}>
              {tags.map((tag) => (
                <li key={`${tag.label}-${tag.tone}`} data-tone={tag.tone || 'neutral'}>
                  {tag.label}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="landing-price-rate">
          {pstn ? (
            <>
              <span className="landing-price-value">{formatInrAmount(pstn.inrPerMin)}</span>
              <span className="landing-price-unit">/phone min</span>
              <span className="landing-price-usd">≈ {formatUsdAmount(pstn.usdPerMin)} per minute in USD</span>
            </>
          ) : (
            <span className="landing-price-unavailable">This rate is shown in your workspace.</span>
          )}
        </div>

        <div className="landing-price-channels">
          <span>
            Phone number rental{' '}
            {numberMonthly.inr != null ? (
              <>
                <strong>{formatInrAmount(numberMonthly.inr)}</strong>/month
              </>
            ) : (
              'rate in workspace'
            )}
          </span>
        </div>

        <button type="button" className="landing-button landing-price-action" onClick={onSelectPlan}>
          Choose {tier.label}
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </article>
    </div>
  );
}

export function PricingCards({ catalog, loading, error, onRetry, onSelectPlan }) {
  const tiers = pricedTiers(catalog);
  const numberMonthly = catalogNumberMonthly(catalog);
  const featuredStyle = typeof catalog?.featuredStyle === 'string' ? catalog.featuredStyle : undefined;

  if (loading && !catalog) {
    return (
      <div className="landing-price-grid" aria-busy="true" aria-label="Loading published prices">
        {[0, 1, 2].map((key) => <div key={key} className="landing-price-skeleton" />)}
      </div>
    );
  }

  if (!tiers.length) {
    return (
      <div className="landing-price-state" role="status" data-testid="landing-pricing-unavailable">
        <h3>Live pricing is temporarily unavailable.</h3>
        <p>
          The current rates could not be loaded. Prices are always shown in your workspace before
          you make a call, and checkout confirms the charge before payment.
        </p>
        <div className="landing-price-state-actions">
          {error ? (
            <button type="button" className="landing-text-link" onClick={onRetry}>
              Try again
            </button>
          ) : null}
          <button type="button" className="landing-button" onClick={onSelectPlan}>
            Open workspace pricing
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="landing-price-grid" data-testid="landing-pricing-cards">
      {tiers.map((tier, index) => (
        <TierCard
          key={tier.id}
          tier={tier}
          index={index}
          numberMonthly={numberMonthly}
          featuredStyle={featuredStyle}
          onSelectPlan={onSelectPlan}
        />
      ))}
    </div>
  );
}
