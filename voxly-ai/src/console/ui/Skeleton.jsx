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
    <div className="space-y-6" data-testid="module-skeleton" aria-busy="true">
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
