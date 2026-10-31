import React from 'react';

/**
 * SolidCard / Card — the one surface for grouped content. White, hairline border,
 * card radius (16px). `variant`: default | subtle | dark. Props unchanged.
 */
export function SolidCard({
  children,
  className = '',
  hover = false,
  padding = 'p-5 sm:p-6',
  variant = 'default',
  onClick,
  as: Tag = 'div',
  ...props
}) {
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

  return (
    <Tag
      onClick={onClick}
      className={`${variantStyles[variant] || variantStyles.default} rounded-card ${padding} ${hoverStyles} ${className}`}
      {...props}
    >
      {children}
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
