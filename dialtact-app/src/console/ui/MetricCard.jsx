import React from 'react';

/**
 * MetricCard UI Primitive
 * Displays a single KPI metric with monospace numbers and percentage trend indicator.
 * Standardized to the landing page craft color palette and typography.
 */
export function MetricCard({
  title,
  value,
  trend = null,
  trendLabel = 'vs last week',
  icon: Icon = null,
  subtitle = null,
  className = ''
}) {
  const isPositive = trend && trend.startsWith('+');

  return (
    <div className={`bg-white border border-[#E4E2EB] rounded-2xl p-5 sm:p-6 shadow-craft-xs hover:border-[#D1CFDB] transition-all ${className}`}>
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className="text-xs font-semibold text-[#524E5E] tracking-wider uppercase">
          {title}
        </span>
        {Icon && (
          <div className="w-8 h-8 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17] shadow-2xs">
            <Icon className="w-4 h-4 text-[#524E5E]" />
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-3 mb-1.5">
        <span className="text-2xl sm:text-3xl font-bold font-mono text-[#0F0E17] tracking-tight">
          {value}
        </span>
        {trend && (
          <span
            className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-md text-[11px] font-mono font-semibold ${
              isPositive
                ? 'bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]'
                : 'bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA]'
            }`}
          >
            {trend}
          </span>
        )}
      </div>

      {(subtitle || trendLabel) && (
        <div className="text-[11px] text-[#524E5E]">
          {subtitle || trendLabel}
        </div>
      )}
    </div>
  );
}
