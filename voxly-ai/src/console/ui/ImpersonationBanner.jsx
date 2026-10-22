import React from 'react';
import { useAuth } from '../../context/AuthContext';

/** Amber support banner while an admin is impersonating a tenant member. */
export function ImpersonationBanner() {
  const { user, logout } = useAuth();
  const imp = user?.impersonation;
  if (!imp?.actor) return null;

  return (
    <div
      className="shrink-0 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950"
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
          . Actions are audited.
        </p>
        <button
          type="button"
          className="rounded-md border border-amber-400 bg-white px-3 py-1 text-xs font-medium hover:bg-amber-100"
          onClick={() => logout()}
        >
          End support session
        </button>
      </div>
    </div>
  );
}
