import React, { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, AudioLines, Plus } from 'lucide-react';
import Magnet from '@/components/reactbits/Magnet';
import { UsageCalculator } from '../components/UsageCalculator';
import { catalogNumberMonthly, formatInrAmount, formatUsdAmount, pricedTiers, usePricingCatalog } from '../lib/usePricingCatalog';
import { LANDING_FAQS } from '../data/siteContent';
import { api } from '../services/api';
import { BotAnchor } from './ScrollBot';
import SpotlightCard from '@/components/reactbits/SpotlightCard';
import { Reveal, WarmTooltip } from './effects';

/** Published rates from the billing catalog — never a hard-coded price. */
export function PricingSection({ onSelectPlan }) {
  const pricing = usePricingCatalog();
  const tiers = pricedTiers(pricing.data);
  const numberMonthly = catalogNumberMonthly(pricing.data);

  return (
    <section
      id="pricing"
      className="mk-section"
      aria-label="Pricing"
      data-bot-say="Today’s published rates. Each call locks its rate."
      data-bot-gesture="NOD"
      data-bot-state="CONFIDENT"
      data-bot-title="Pricing"
    >
      <div className="mk-container">
        <div className="mk-head">
          <div>
            <h2 className="mk-h2">Pay per minute. See the rate first.</h2>
            <p className="mk-lede">
              Fund your wallet, pick an available voice tier, and review the exact per-minute phone rate before calling.{' '}
              <WarmTooltip label="Checkout confirms any applicable tax before you pay. Available tiers depend on your workspace.">What about tax?</WarmTooltip>
            </p>
          </div>
          <a className="mk-link" href="/#usage-calculator" onClick={(e) => { e.preventDefault(); const el = document.getElementById('usage-calculator'); if (window.__dialtactLenis) window.__dialtactLenis.scrollTo(el, { offset: -72 }); else el?.scrollIntoView({ behavior: 'smooth' }); }}>
            Estimate your usage <ArrowRight size={16} aria-hidden="true" />
          </a>
        </div>

        {pricing.loading && !pricing.data ? (
          <div className="mk-price-grid" aria-busy="true" aria-label="Loading published prices">
            {[0, 1, 2].map((key) => <div key={key} className="mk-price-skeleton" />)}
          </div>
        ) : !tiers.length ? (
          <div className="mk-card mk-price-state" role="status" data-testid="mk-pricing-unavailable">
            <h3>Live pricing is temporarily unavailable.</h3>
            <p>The current rates could not be loaded. Prices are always shown in your workspace before you make a call, and checkout confirms the charge before payment.</p>
            <div>
              {pricing.error ? <button type="button" className="mk-btn mk-btn-ghost" onClick={pricing.reload}>Try again</button> : null}
              <button type="button" className="mk-btn mk-btn-primary" onClick={onSelectPlan}>Open workspace pricing <ArrowRight size={16} aria-hidden="true" /></button>
            </div>
          </div>
        ) : (
          <div className="mk-price-grid" data-testid="mk-pricing-cards">
            {tiers.map((tier, index) => {
              const featured = tier.featured === true;
              const tags = Array.isArray(tier.tags) ? tier.tags : [];
              return (
                <Reveal key={tier.id} delay={index * 0.08} className="h-full">
                  {/* React Bits Spotlight Card: a soft light follows the pointer and spills onto the neighbours. */}
                  <SpotlightCard
                    theme={featured ? 'light' : 'dark'}
                    intensity={featured ? 0.35 : 0.2}
                    spotlightSize={320}
                    proximity={120}
                    className={`mk-price h-full${featured ? ' is-featured' : ''}`}
                    data-tier={tier.id}
                    data-bot-hover={tier.pstn ? `${tier.label}: ${formatInrAmount(tier.pstn.inrPerMin)} a phone minute.` : `${tier.label}: the rate is in your workspace.`}
                  >
                    <h3>{tier.label}</h3>
                    {tags.length > 0 && (
                      <ul className="mk-price-tags" aria-label={`${tier.label} highlights`}>
                        {tags.map((tag) => <li key={`${tag.label}-${tag.tone}`} className="mk-tag">{tag.label}</li>)}
                      </ul>
                    )}
                    {tier.pstn ? (
                      <>
                        <p className="mk-price-value">{formatInrAmount(tier.pstn.inrPerMin)}<small>/ phone min</small></p>
                        <p className="mk-price-usd">≈ {formatUsdAmount(tier.pstn.usdPerMin)} per minute in USD</p>
                      </>
                    ) : (
                      <p className="mk-price-row">This rate is shown in your workspace.</p>
                    )}
                    <p className="mk-price-row">
                      Phone number rental{' '}
                      {numberMonthly.inr != null ? <><strong>{formatInrAmount(numberMonthly.inr)}</strong>/month</> : 'rate in workspace'}
                    </p>
                    <button type="button" className={`mk-btn ${featured ? 'mk-btn-primary' : 'mk-btn-ghost'}`} style={{ marginTop: '1.75rem' }} onClick={onSelectPlan}>
                      Choose {tier.label} <ArrowRight size={16} aria-hidden="true" />
                    </button>
                  </SpotlightCard>
                </Reveal>
              );
            })}
          </div>
        )}
        <p className="mk-caption">Rates are per minute. Each call locks its rate when it starts, and checkout confirms the applicable tax before payment.</p>

        <div id="usage-calculator" className="mk-sheet" style={{ scrollMarginTop: '5rem' }}>
          <UsageCalculator catalog={pricing.data} loading={pricing.loading} error={pricing.error} onRetry={pricing.reload} onSelectPlan={onSelectPlan} syncUrl />
        </div>
      </div>
    </section>
  );
}

/** The FAQ, plus the matching FAQPage structured data (prerendered into the HTML). */
export function FaqSection() {
  const [open, setOpen] = useState(0);
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: LANDING_FAQS.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })),
  };
  return (
    <section
      id="faq"
      className="mk-section"
      aria-label="Frequently asked questions"
      data-bot-say="If I don’t know, I say so."
      data-bot-bubble="below"
      data-bot-gesture="REACH_RIGHT"
      data-bot-state="LISTENING"
      data-bot-title="FAQ"
      data-bot-side="left"
    >
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema).replace(/</g, '\\u003c') }} />
      <div className="mk-container mk-faq">
        <div>
          <h2 className="mk-h2">A few things you might be <span className="mk-dim-text">wondering.</span></h2>
          <div className="mk-faq-stage"><BotAnchor /></div>
        </div>
        <div>
          {LANDING_FAQS.map(([question, answer], index) => {
            const expanded = open === index;
            const id = `mk-faq-${index}`;
            return (
              <div key={question} className="mk-faq-item">
                <h3>
                  <button type="button" aria-expanded={expanded} aria-controls={id} data-bot-click-move="NOD" onClick={() => setOpen(expanded ? -1 : index)}>
                    {question}<Plus size={20} aria-hidden="true" />
                  </button>
                </h3>
                <AnimatePresence initial={false}>
                  {expanded && (
                    <motion.div id={id} role="region" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }} style={{ overflow: 'hidden' }}>
                      <p>{answer}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function FinalCtaSection({ onGetStarted }) {
  return (
    <section
      className="mk-section mk-final"
      aria-label="Get started with Dialtact"
      data-bot-say="Let’s build yours."
      data-bot-gesture="CELEBRATE"
      data-bot-state="EXCITED"
      data-bot-title="Ready?"
    >
      <div className="mk-container">
        <div className="mk-statement-stage"><BotAnchor /></div>
        <h2 className="mk-final-title">Give your next caller a better hello.</h2>
        <p>Create your agent in the browser, test it with your own script, then put it on a number when it sounds right.</p>
        <div className="mk-actions">
          <Magnet padding={70} magnetStrength={3}>
            <a href="/signin" className="mk-btn mk-btn-primary mk-btn-lg" data-bot-hover="I’m ready when you are." data-bot-hover-move="HOP" onClick={(event) => { event.preventDefault(); onGetStarted(); }}>
              Create your own agent <ArrowRight size={18} aria-hidden="true" />
            </a>
          </Magnet>
        </div>
      </div>
    </section>
  );
}

const SOCIAL_LABELS = { twitter: 'X', linkedin: 'LinkedIn', youtube: 'YouTube', github: 'GitHub', discord: 'Discord' };
const FOOTER_GROUPS = [
  ['Product', [['How it works', '/#how-it-works'], ['Hear a real call', '/#demo'], ['Use cases', '/#industries'], ['Pricing', '/#pricing']]],
  ['Company', [['About Dialtact', '/company'], ['Contact & support', '/support']]],
  ['Resources', [['Common questions', '/#faq'], ['Security', '/security'], ['Privacy', '/privacy'], ['Terms', '/terms']]],
];

export function MarketingFooter({ onNavigatePage }) {
  const [socialLinks, setSocialLinks] = useState({});
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    api.support.getConfig().then((config) => { if (mounted.current) setSocialLinks(config?.socialLinks || {}); }).catch(() => {});
    return () => { mounted.current = false; };
  }, []);
  const navigate = (target) => (event) => {
    if (!onNavigatePage) return;
    event.preventDefault();
    onNavigatePage(target.replace(/^\/?#?/, ''));
  };
  const socials = Object.entries(SOCIAL_LABELS).filter(([key]) => /^https?:\/\//i.test(socialLinks[key] || ''));

  return (
    <footer className="mk-footer">
      <div className="mk-container">
        <div className="mk-footer-grid">
          <div>
            <a className="mk-brand" href="/" onClick={navigate('/')}><span className="mk-brand-mark"><AudioLines size={17} aria-hidden="true" /></span>Dialtact</a>
            <p>AI voice agents that answer every call, book the next step and log the conversation.</p>
            {socials.length > 0 && (
              <div className="mk-socials" data-testid="footer-social-links">
                {socials.map(([key, label]) => <a key={key} href={socialLinks[key]} target="_blank" rel="noopener noreferrer" aria-label={`Dialtact on ${label}`}>{label}</a>)}
              </div>
            )}
          </div>
          {FOOTER_GROUPS.map(([title, links]) => (
            <nav key={title} aria-label={title}>
              <h2>{title}</h2>
              <ul>{links.map(([label, href]) => <li key={href}><a href={href} onClick={navigate(href)}>{label}</a></li>)}</ul>
            </nav>
          ))}
        </div>
        <div className="mk-footer-bottom">
          <span>© {new Date().getFullYear()} Dialtact. All rights reserved.</span>
          <span>Built for the way your business talks.</span>
        </div>
      </div>
    </footer>
  );
}
