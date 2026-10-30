import React from 'react';

/**
 * Button — the one button for the console (TactileButton is the same component;
 * both names are exported so existing callers keep working).
 *
 * Variants: primary (ink, the main action on a surface) · brand (accent, at most
 * one per screen) · secondary/white/outline (bordered) · ghost (quiet, inline) ·
 * danger (destructive only) · success (confirming a positive state).
 * Sizes: xs · sm · md · lg · icon. Text is never below 12px.
 */
export function TactileButton({
  children,
  variant = 'primary',
  size = 'md',
  onClick,
  disabled = false,
  loading = false,
  className = '',
  type = 'button',
  icon: Icon = null,
  ...props
}) {
  const baseStyles =
    'inline-flex min-h-[44px] sm:min-h-0 items-center justify-center gap-2 font-semibold rounded-control transition-[background-color,border-color,color,transform] duration-150 select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-canvas disabled:opacity-45 disabled:pointer-events-none active:scale-[0.98] motion-reduce:active:scale-100';

  const sizeStyles = {
    xs: 'px-2.5 py-1 text-meta',
    sm: 'px-3 py-1.5 text-meta',
    md: 'px-4 py-2 text-ui',
    lg: 'px-5 py-2.5 text-copy',
    icon: 'p-2',
  };

  const variantStyles = {
    primary: 'bg-ink hover:bg-[#232130] text-white border border-transparent shadow-craft-xs',
    brand: 'bg-accent hover:bg-accent-hover text-white border border-transparent shadow-craft-xs',
    secondary: 'bg-surface hover:bg-canvas text-ink border border-line hover:border-line-strong shadow-craft-xs',
    white: 'bg-surface hover:bg-canvas text-ink border border-line shadow-craft-xs',
    ghost: 'bg-transparent hover:bg-surface-subtle text-fg-body hover:text-ink border border-transparent',
    danger: 'bg-danger-soft hover:bg-[#FEE2E2] text-danger-fg border border-danger-line',
    success: 'bg-success-soft hover:bg-[#D1FAE5] text-success-fg border border-success-line',
    outline: 'bg-transparent hover:bg-canvas text-ink border border-line',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${baseStyles} ${sizeStyles[size] || sizeStyles.md} ${variantStyles[variant] || variantStyles.primary} ${className}`}
      {...props}
    >
      {loading ? (
        <svg
          className="animate-spin -ml-0.5 h-3.5 w-3.5 text-current"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      ) : Icon ? (
        <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  );
}

export const Button = TactileButton;
