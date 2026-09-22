import React from 'react';

export function SectionHeading({
  badge,
  title,
  highlight,
  subtitle,
  centered = true,
  className = '',
}) {
  return (
    <div className={`mb-12 sm:mb-16 ${centered ? 'text-center max-w-3xl mx-auto' : 'max-w-2xl'} ${className}`}>
      {badge && (
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
          <span>{badge}</span>
        </div>
      )}
      <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.15]">
        {title}{' '}
        {highlight && (
          <span className="text-[#0F0E17]">
            {highlight}
          </span>
        )}
      </h2>
      {subtitle && (
        <p className="mt-4 text-base sm:text-lg text-[#524E5E] leading-relaxed">
          {subtitle}
        </p>
      )}
    </div>
  );
}
