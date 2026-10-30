import React from 'react';
import { useAuth } from '../../context/AuthContext';

/** Amber support banner while an admin is impersonating a tenant member. */
export function ImpersonationBanner() {
  const { user, logout } = useAuth();
  const imp = user?.impersonation;
  if (!imp?.actor) return null;

  return (
    <div
      className="shrink-0 border-b border-warning-line bg-warning-soft px-4 py-2 text-ui text-warning-fg"
      data-testid="impersonation-banner"
      role="status"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2">
        <p>
          Support session: admin <strong>{imp.actor}</strong> is acting as{' '}
          <strong>{imp.userEmail || user?.email}</strong>
          {imp.tenantName ? (
            <>
              {' '}
              in <strong>{imp.tenantName}</strong>
            </>
          ) : null}
          . Everything done in this session is recorded.
        </p>
        <button
          type="button"
          className="min-h-[36px] rounded-control border border-warning-line bg-surface px-3 py-1 text-ui font-medium hover:bg-warning-soft"
          onClick={() => logout()}
        >
          End support session
        </button>
      </div>
    </div>
  );
}
