import React from 'react';
import { Skeleton } from '../../ui/Skeleton';

const WIDTHS = [
  ['w-3/4', 'w-1/2', true],
  ['w-2/3', 'w-2/5', false],
  ['w-4/5', 'w-1/3', true],
  ['w-1/2', 'w-1/4', false],
  ['w-3/5', 'w-2/5', false],
];

/** Feed rows while loading: avatar, sentence, summary line, meta and an action — the same shape as `FeedItem`. */
export function FeedSkeleton({ rows = 5, withHeader = true }) {
  return (
    <div aria-busy="true" aria-label="Loading activity" data-testid="home-feed-skeleton">
      {withHeader && (
        <div className="px-4 pt-3 pb-1 sm:px-5">
          <Skeleton className="h-3 w-12" />
        </div>
      )}
      <ul className="divide-y divide-line">
        {Array.from({ length: rows }).map((_, i) => {
          const [line, detail, action] = WIDTHS[i % WIDTHS.length];
          return (
            <li key={i} className="flex gap-3 px-4 py-3.5 sm:px-5">
              <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className={`h-4 ${line}`} />
                <Skeleton className={`h-3 ${detail}`} />
                <div className="flex gap-2 pt-0.5">
                  <Skeleton className="h-3 w-14" />
                  <Skeleton className="h-3 w-20" />
                </div>
                {action && (
                  <div className="flex gap-2 pt-1">
                    <Skeleton className="h-7 w-20 rounded-control" />
                    <Skeleton className="h-7 w-16 rounded-control" />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** The rail's cards while the workspace loads. */
export function RailSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="space-y-3 rounded-card border border-line bg-surface p-4">
        <Skeleton className="h-4 w-28" />
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3 w-32" />
          </div>
        </div>
      </div>
      <div className="space-y-3 rounded-card border border-line bg-surface p-4">
        <Skeleton className="h-4 w-16" />
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-control" />)}
        </div>
      </div>
      <Skeleton className="h-24 w-full rounded-card" />
    </div>
  );
}
