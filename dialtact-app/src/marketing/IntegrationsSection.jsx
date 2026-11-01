import React from 'react';
import LogoLoop from '@/components/reactbits/LogoLoop';
import { BotAnchor } from './ScrollBot';
import { INTEGRATIONS } from './integrations';

/** A brand's logo in white, or its initials where there is no logo to use. */
function Logo({ item, size = 24 }) {
  if (!item.icon) return <span className="mk-int-mark" aria-hidden="true">{item.mark}</span>;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={item.icon.path} />
    </svg>
  );
}

const INNER = INTEGRATIONS.filter((_, i) => i % 3 === 0).slice(0, 8);
const OUTER = INTEGRATIONS.filter((_, i) => i % 3 !== 0).slice(0, 12);
const LOOP = INTEGRATIONS.map((item) => ({ node: <Logo item={item} size={22} />, title: item.name, ariaLabel: item.name }));

function Ring({ items, className }) {
  return (
    <div className={`mk-orbit-ring ${className}`}>
      {items.map((item, i) => (
        <div key={item.name} className="mk-orbit-item" style={{ '--a': `${(360 / items.length) * i}deg` }}>
          <span className="mk-orbit-chip" title={item.name} data-bot-hover={`I can work in ${item.name}.`}><Logo item={item} /></span>
        </div>
      ))}
    </div>
  );
}

/**
 * The tools an agent works in, from the server's catalog: the mascot stands at the centre
 * of an orbit of them, and every one of the 28 runs past underneath (React Bits LogoLoop).
 */
export function IntegrationsSection() {
  return (
    <section
      id="integrations"
      className="mk-section mk-integrations"
      aria-labelledby="mk-integrations-title"
      data-bot-say="I work inside your calendar, CRM, helpdesk and inbox."
      data-bot-gesture="PRESENT"
      data-bot-state="HAPPY"
      data-bot-side="center"
    >
      <div className="mk-container">
        <h2 id="mk-integrations-title" className="mk-h2 mk-center">Works with the tools you already use.</h2>
        <p className="mk-lede mk-center">
          Calendars, CRMs, helpdesks and inboxes. It books into your calendar, updates your CRM and sends the confirmation while the caller is still on the line.
        </p>
        <div className="mk-orbit" aria-hidden="true">
          <Ring items={OUTER} className="is-outer" />
          <Ring items={INNER} className="is-inner" />
          <div className="mk-orbit-core"><BotAnchor /></div>
        </div>
      </div>
      <LogoLoop
        logos={LOOP}
        speed={36}
        logoHeight={22}
        gap={56}
        labels="inline"
        pauseOnHover
        fadeOut
        intro={false}
        ariaLabel="Integrations"
        className="mk-int-loop"
      />
    </section>
  );
}
