import React from 'react';

/** Lightweight pulse blocks for sections that are still loading. */
export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-lg bg-[#E4E2EB]/80 ${className}`} />;
}

export function CatalogSkeleton({ rows = 4 }) {
  return (
    <div className="space-y-2" data-testid="catalog-skeleton" aria-busy="true" aria-label="Loading numbers">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="p-3.5 rounded-xl border border-[#E4E2EB] bg-white flex items-center justify-between gap-4"
        >
          <div className="flex items-center gap-3 flex-1">
            <Skeleton className="w-8 h-8 rounded-lg shrink-0" />
            <div className="space-y-2 flex-1">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-2.5 w-24" />
            </div>
          </div>
          <Skeleton className="h-7 w-20 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

export function ModuleSkeleton({ cards = 3 }) {
  return (
    <div className="space-y-6" data-testid="module-skeleton" aria-busy="true" aria-label="Loading module">
      <div className="space-y-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-3 w-80 max-w-full" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {Array.from({ length: cards }).map((_, i) => (
          <div key={i} className="p-4 rounded-2xl border border-[#E4E2EB] bg-white space-y-3">
            <Skeleton className="h-2.5 w-20" />
            <Skeleton className="h-7 w-16" />
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-[#E4E2EB] bg-white p-4 space-y-3">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}

/** Standard table rows skeleton matching 4-to-6 column layouts */
export function TableRowsSkeleton({ rows = 5, cols = 5 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading table rows">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3.5 px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1">
            <Skeleton className="w-8 h-8 rounded-lg shrink-0" />
            <div className="space-y-1.5 flex-1">
              <Skeleton className="h-3 w-36" />
              <Skeleton className="h-2 w-24" />
            </div>
          </div>
          {cols >= 3 && <Skeleton className="h-4 w-24 hidden sm:block" />}
          {cols >= 4 && <Skeleton className="h-4 w-20 hidden md:block" />}
          {cols >= 5 && <Skeleton className="h-5 w-16 rounded-full" />}
        </div>
      ))}
    </div>
  );
}

/** Metrics KPI card grid skeleton */
export function MetricsGridSkeleton({ count = 4 }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse" aria-busy="true" aria-label="Loading metrics">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 rounded-2xl border border-[#E4E2EB] bg-white space-y-3">
          <div className="flex items-center justify-between">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="w-7 h-7 rounded-lg" />
          </div>
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-2.5 w-16" />
        </div>
      ))}
    </div>
  );
}

/** AI Employee card grid skeleton matching EmployeesModule cards */
export function AgentCardsGridSkeleton({ count = 3 }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 animate-pulse" aria-busy="true" aria-label="Loading agents">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-4 shadow-craft-xs">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-3">
              <Skeleton className="w-11 h-11 rounded-2xl shrink-0" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-20" />
              </div>
            </div>
            <Skeleton className="h-5 w-14 rounded-full" />
          </div>
          <div className="grid grid-cols-2 gap-3 py-1">
            <div className="space-y-1">
              <Skeleton className="h-2.5 w-14" />
              <Skeleton className="h-3.5 w-24" />
            </div>
            <div className="space-y-1">
              <Skeleton className="h-2.5 w-14" />
              <Skeleton className="h-3.5 w-24" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 py-2 border-t border-[#E4E2EB]">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
          <div className="flex items-center gap-2 pt-2 border-t border-[#E4E2EB]">
            <Skeleton className="h-8 flex-1 rounded-xl" />
            <Skeleton className="h-8 flex-1 rounded-xl" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Agent Studio Header Skeleton */
export function AgentStudioHeaderSkeleton() {
  return (
    <div className="p-4 sm:p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-4 animate-pulse" aria-busy="true" aria-label="Loading agent studio">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="w-12 h-12 rounded-2xl shrink-0" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-44" />
            <Skeleton className="h-3.5 w-28" />
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <Skeleton className="h-9 w-24 rounded-xl" />
          <Skeleton className="h-9 w-28 rounded-xl" />
        </div>
      </div>
      <div className="flex items-center gap-2 pt-3 border-t border-[#E4E2EB] overflow-x-auto">
        {Array.from({ length: 7 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-24 rounded-xl shrink-0" />
        ))}
      </div>
    </div>
  );
}

/** Agent Studio Script Editor Skeleton */
export function AgentStudioEditorSkeleton() {
  return (
    <div className="p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-4 animate-pulse" aria-busy="true" aria-label="Loading script editor">
      <div className="flex items-center justify-between pb-3 border-b border-[#E4E2EB]">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div className="space-y-2.5 py-2 font-mono">
        <Skeleton className="h-3.5 w-3/4" />
        <Skeleton className="h-3.5 w-1/2" />
        <Skeleton className="h-3.5 w-5/6" />
        <Skeleton className="h-3.5 w-2/3" />
        <Skeleton className="h-3.5 w-4/5" />
        <Skeleton className="h-3.5 w-1/3" />
        <Skeleton className="h-3.5 w-3/5" />
        <Skeleton className="h-3.5 w-2/5" />
      </div>
    </div>
  );
}

/** Campaign Card Skeleton */
export function CampaignCardSkeleton({ count = 3 }) {
  return (
    <div className="space-y-4 animate-pulse" aria-busy="true" aria-label="Loading campaigns">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-4 shadow-craft-xs">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Skeleton className="w-10 h-10 rounded-xl shrink-0" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between">
              <Skeleton className="h-2.5 w-20" />
              <Skeleton className="h-2.5 w-12" />
            </div>
            <Skeleton className="h-2 w-full rounded-full" />
          </div>
          <div className="grid grid-cols-4 gap-2 pt-2 border-t border-[#E4E2EB]">
            <Skeleton className="h-8 w-full rounded-lg" />
            <Skeleton className="h-8 w-full rounded-lg" />
            <Skeleton className="h-8 w-full rounded-lg" />
            <Skeleton className="h-8 w-full rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** DND Registry Table Skeleton */
export function DncTableSkeleton({ rows = 5 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading DNC registry">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 w-36">
            <Skeleton className="h-4 w-28 font-mono" />
          </div>
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-3.5 w-36 hidden sm:block" />
          <Skeleton className="h-3.5 w-20 hidden md:block" />
          <Skeleton className="h-7 w-16 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

/** Calls History Table Skeleton */
export function CallsTableSkeleton({ rows = 6 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading call logs">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3.5 px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <Skeleton className="w-8 h-8 rounded-full shrink-0" />
            <div className="space-y-1 flex-1">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-2.5 w-24" />
            </div>
          </div>
          <Skeleton className="h-5 w-20 rounded-full hidden sm:block" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-3.5 w-14 font-mono hidden md:block" />
          <Skeleton className="h-3.5 w-28 hidden lg:block" />
          <Skeleton className="h-3 w-16 text-right" />
        </div>
      ))}
    </div>
  );
}

/** Call Detail Drawer Skeleton */
export function CallDetailSkeleton() {
  return (
    <div className="p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-4 animate-pulse" aria-busy="true" aria-label="Loading call details">
      <div className="flex items-center justify-between pb-3 border-b border-[#E4E2EB]">
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-5 w-36" />
        </div>
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
      <Skeleton className="h-12 w-full rounded-xl" />
      <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-4/5" />
      </div>
      <div className="space-y-2 pt-2">
        <Skeleton className="h-10 w-3/4 rounded-xl" />
        <Skeleton className="h-10 w-2/3 ml-auto rounded-xl" />
        <Skeleton className="h-10 w-4/5 rounded-xl" />
      </div>
    </div>
  );
}

/** Kanban Stage Columns Skeleton */
export function KanbanSkeleton({ columns = 5 }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 animate-pulse" aria-busy="true" aria-label="Loading kanban pipeline">
      {Array.from({ length: columns }).map((_, colIdx) => (
        <div key={colIdx} className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-2xl p-3 space-y-3">
          <div className="flex justify-between items-center pb-2 border-b border-[#E4E2EB]">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-6 rounded-full" />
          </div>
          <div className="space-y-2">
            <div className="bg-white border border-[#E4E2EB] rounded-xl p-3 space-y-2 shadow-2xs">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="h-2.5 w-1/2" />
              <div className="flex justify-between pt-1">
                <Skeleton className="h-4 w-12 rounded-full" />
                <Skeleton className="h-4 w-14" />
              </div>
            </div>
            <div className="bg-white border border-[#E4E2EB] rounded-xl p-3 space-y-2 shadow-2xs">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-2.5 w-1/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Leads Table View Skeleton */
export function LeadsTableSkeleton({ rows = 5 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading leads">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 px-4 flex items-center justify-between gap-4">
          <div className="space-y-1 w-40">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-2.5 w-20" />
          </div>
          <Skeleton className="h-3.5 w-28 font-mono hidden sm:block" />
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-3.5 w-36 hidden md:block" />
          <Skeleton className="h-7 w-16 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

/** Billing Balance Card Skeleton */
export function BillingBalanceSkeleton() {
  return (
    <div className="p-5 rounded-2xl border border-[#E4E2EB] bg-white space-y-3 animate-pulse" aria-busy="true" aria-label="Loading balance">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3.5 w-28" />
        <Skeleton className="w-8 h-8 rounded-lg" />
      </div>
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

/** Invoices Table Skeleton */
export function InvoiceRowsSkeleton({ rows = 3 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading invoices">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 px-4 flex items-center justify-between gap-4">
          <Skeleton className="h-3.5 w-24 font-mono" />
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-3.5 w-16 font-mono" />
          <Skeleton className="h-7 w-20 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

/** Transactions Table Skeleton */
export function TransactionRowsSkeleton({ rows = 6 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading transactions">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 px-4 flex items-center justify-between gap-4">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="h-3.5 w-32 font-mono hidden sm:block" />
          <Skeleton className="h-3.5 w-16 font-mono font-semibold" />
        </div>
      ))}
    </div>
  );
}

/** Audio Waveform Equalizer Shimmer */
export function WaveformSkeleton() {
  return (
    <div className="flex items-end gap-1 h-6 py-1 px-2 bg-[#F0EEF6] rounded-lg" aria-hidden="true">
      {[40, 70, 30, 90, 60, 100, 50, 80].map((h, i) => (
        <div
          key={i}
          style={{ height: `${h}%` }}
          className="w-1 bg-[#6344E7]/40 rounded-full animate-pulse"
        />
      ))}
    </div>
  );
}

/** Topbar Balance Pill Skeleton */
export function TopbarBalanceSkeleton() {
  return (
    <span className="inline-block h-4 w-14 bg-[#E4E2EB]/80 rounded-md animate-pulse" aria-hidden="true" />
  );
}

/** Phone Number Table Row Skeleton */
export function PhoneNumberRowSkeleton({ rows = 3 }) {
  return (
    <div className="divide-y divide-[#E4E2EB] animate-pulse" aria-busy="true" aria-label="Loading phone lines">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 px-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Skeleton className="w-8 h-8 rounded-lg shrink-0" />
            <div className="space-y-1">
              <Skeleton className="h-4 w-32 font-mono" />
              <Skeleton className="h-2.5 w-20" />
            </div>
          </div>
          <Skeleton className="h-6 w-32 rounded-lg hidden sm:block" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-4 w-12 font-mono" />
        </div>
      ))}
    </div>
  );
}

/** Admin Overview Metrics Skeleton */
export function AdminMetricsSkeleton({ count = 4 }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 animate-pulse" aria-busy="true" aria-label="Loading admin overview">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 rounded-2xl border border-[#E4E2EB] bg-white space-y-3">
          <div className="flex items-center gap-2">
            <Skeleton className="w-3.5 h-3.5 rounded" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-7 w-16 font-mono" />
        </div>
      ))}
    </div>
  );
}
