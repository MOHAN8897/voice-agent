import React from 'react';

/**
 * Avatar — an AI employee's (or contact's) initial on a stable colour.
 *
 *   <Avatar name="Meera" live />      // green ring that pulses while on a call
 *   <Avatar name="Hima" size="sm" />
 *   <Avatar icon={Wallet} tone="warning" />   // system items: wallet, numbers…
 *
 * The colour is derived from the name so the same agent always looks the same
 * across the console. The live ring respects prefers-reduced-motion.
 */
const PALETTE = [
  'bg-[#EDE9FE] text-[#5B21B6]',
  'bg-[#E0F2FE] text-[#075985]',
  'bg-[#DCFCE7] text-[#166534]',
  'bg-[#FEF3C7] text-[#92400E]',
  'bg-[#FCE7F3] text-[#9D174D]',
  'bg-[#E0E7FF] text-[#3730A3]',
  'bg-[#CCFBF1] text-[#115E59]',
  'bg-[#FFE4E6] text-[#9F1239]',
];

const ICON_TONES = {
  neutral: 'bg-surface-subtle text-fg-body',
  success: 'bg-success-soft text-success-fg',
  warning: 'bg-warning-soft text-warning-fg',
  danger: 'bg-danger-soft text-danger-fg',
  info: 'bg-info-soft text-info-fg',
  accent: 'bg-accent-soft text-accent-fg',
  live: 'bg-success-soft text-success-fg',
};

const SIZES = {
  xs: 'h-6 w-6 text-meta',
  sm: 'h-8 w-8 text-ui',
  md: 'h-10 w-10 text-copy',
  lg: 'h-12 w-12 text-title',
};

export function avatarColor(name) {
  const text = String(name || '?');
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export function Avatar({ name = '', icon: Icon = null, tone = 'neutral', size = 'md', live = false, className = '', title = null }) {
  const initial = String(name || '').trim().charAt(0).toUpperCase() || '?';
  const color = Icon ? ICON_TONES[tone] || ICON_TONES.neutral : avatarColor(name);
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${SIZES[size] || SIZES.md} ${color} ${
        live ? 'ring-2 ring-success ring-offset-2 ring-offset-surface avatar-live-ring' : ''
      } ${className}`}
      title={title || name || undefined}
      aria-hidden={title || name ? undefined : 'true'}
    >
      {Icon ? <Icon className="h-[45%] w-[45%]" aria-hidden="true" /> : initial}
      {live && (
        <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-success" aria-hidden="true" />
      )}
    </span>
  );
}
