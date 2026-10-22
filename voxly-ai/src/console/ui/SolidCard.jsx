import React from 'react';

/**
 * Emil Kowalski Craft Solid Card
 * Clean solid card surface with hairline #E4E2EB border, subtle depth, and intentional padding.
 */
export function SolidCard({
  children,
  className = '',
  hover = false,
  padding = 'p-5 sm:p-6',
  variant = 'default', // 'default' (white) | 'subtle' (#F0EEF6) | 'dark' (#0F0E17 for telemetry/audio monitors)
  onClick,
  ...props
}) {
  const variantStyles = {
    default: 'bg-white border border-[#E4E2EB] text-[#0F0E17] shadow-craft-xs',
    subtle: 'bg-[#F0EEF6] border border-[#E4E2EB] text-[#0F0E17]',
    dark: 'bg-[#0F0E17] border border-[#E4E2EB]/15 text-white shadow-craft-sm'
  };

  const hoverStyles = hover
    ? variant === 'dark'
      ? 'hover:border-white/20 transition-all cursor-pointer'
      : 'hover:border-[#D1CFDB] hover:shadow-craft-sm transition-all cursor-pointer'
    : '';

  return (
    <div
      onClick={onClick}
      className={`${variantStyles[variant] || variantStyles.default} rounded-2xl ${padding} ${hoverStyles} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
