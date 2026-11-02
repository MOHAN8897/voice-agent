import React from 'react';
import { useReducedMotion } from 'framer-motion';
import SpotlightCard from '@/components/reactbits/SpotlightCard';
import { BorderBeam } from '@/components/ui/border-beam';

/**
 * SolidCard / Card — the one surface for grouped content. White, hairline border,
 * card radius (16px). `variant`: default | subtle | dark.
 *
 * `spotlight` (default variant only): a faint accent light follows the pointer and
 * catches the card's edge (React Bits Spotlight Card) — for cards people pick between,
 * like AI employees and integrations. `beam`: a slow accent light runs around the edge
 * (Magic UI Border Beam) — for the one first-run call to action on a screen. Both are
 * off under reduced motion (DESIGN.md → Motion).
 */
export function SolidCard({
  children,
  className = '',
  hover = false,
  padding = 'p-5 sm:p-6',
  variant = 'default',
  onClick,
  as: Tag = 'div',
  spotlight = false,
  beam = false,
  ...props
}) {
  const reduce = useReducedMotion();
  const variantStyles = {
    default: 'bg-surface border border-line text-ink shadow-craft-xs',
    subtle: 'bg-surface-subtle border border-line text-ink',
    dark: 'bg-ink border border-white/10 text-white shadow-craft-sm',
  };

  const hoverStyles = hover
    ? variant === 'dark'
      ? 'hover:border-white/20 transition-colors cursor-pointer'
      : 'hover:border-line-strong hover:shadow-craft-sm transition-[border-color,box-shadow] cursor-pointer'
    : '';

  const classes = `${variantStyles[variant] || variantStyles.default} rounded-card ${padding} ${hoverStyles} ${className}`;

  if (spotlight && variant === 'default' && !reduce) {
    return (
      <SpotlightCard
        theme="light"
        spotlightColor="#6344E7"
        intensity={0.06}
        spotlightSize={280}
        borderGlow={0.5}
        proximity={60}
        flare={false}
        onClick={onClick}
        className={classes}
        // The card keeps its own hairline and shadow; the spotlight only adds light.
        style={{ '--spotlight-card-surface': 'var(--surface, #ffffff)', '--spotlight-card-border': 'transparent', '--spotlight-card-shadow': 'none' }}
        {...props}
      >
        {children}
      </SpotlightCard>
    );
  }

  return (
    <Tag
      onClick={onClick}
      className={`${classes}${beam && !reduce ? ' relative overflow-hidden' : ''}`}
      {...props}
    >
      {children}
      {beam && !reduce && <BorderBeam size={90} duration={9} colorFrom="#6344E7" colorTo="#C9BCFF" borderWidth={1.5} />}
    </Tag>
  );
}

export const Card = SolidCard;

/**
 * Section — a titled card. Title is sentence case, 16px; description is one line
 * of plain language; `actions` sit on the right (wrap below on phones).
 *
 *   <Section title="Active agents" description="Who is working right now" actions={<Button…/>}>…</Section>
 */
export function Section({
  title,
  description = null,
  actions = null,
  children,
  className = '',
  padding = 'p-5 sm:p-6',
  headingLevel = 2,
  ...props
}) {
  const Heading = `h${headingLevel}`;
  return (
    <SolidCard padding={padding} className={className} {...props}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <Heading className="text-title text-ink">{title}</Heading>}
            {description && <p className="mt-0.5 text-ui text-fg-muted">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </SolidCard>
  );
}
