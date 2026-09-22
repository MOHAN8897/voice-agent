import React from 'react';

/**
 * StatusBadge UI Primitive
 * Semantic pill indicator with strict WCAG AA contrast for light backgrounds.
 */
export function StatusBadge({ status, size = 'sm', className = '' }) {
  const norm = String(status || '').toLowerCase();

  let styles = 'bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]';
  let dotColor = 'bg-[#524E5E]';
  let label = status;

  if (norm === 'active' || norm === 'qualified' || norm === 'meeting booked' || norm === 'resolved') {
    styles = 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]';
    dotColor = 'bg-[#10B981]';
  } else if (norm === 'paused' || norm === 'draft' || norm === 'idle' || norm === 'new') {
    styles = 'bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]';
    dotColor = 'bg-[#F59E0B]';
  } else if (norm === 'inbound') {
    styles = 'bg-[#EFF6FF] text-[#1E40AF] border-[#BFDBFE]';
    dotColor = 'bg-[#3B82F6]';
  } else if (norm === 'outbound') {
    styles = 'bg-[#F5F3FF] text-[#5B21B6] border-[#DDD6FE]';
    dotColor = 'bg-[#8B5CF6]';
  } else if (norm === 'unqualified' || norm === 'failed' || norm === 'cancelled') {
    styles = 'bg-[#FEF2F2] text-[#991B1B] border-[#FECACA]';
    dotColor = 'bg-[#EF4444]';
  } else if (norm === 'running') {
    styles = 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]';
    dotColor = 'bg-[#10B981] animate-pulse';
  }

  const sizeClass = size === 'xs' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold rounded-md border ${sizeClass} ${styles} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      <span>{label}</span>
    </span>
  );
}
