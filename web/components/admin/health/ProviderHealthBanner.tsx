"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useAdminResource } from "@/lib/useAdminResource";
import { relativeTime } from "@/components/admin/accounts/model";
import { PROVIDER_HEALTH_PATH, type ProviderHealth } from "@/components/admin/health/types";

/**
 * Overview banner: shown only while a stack vendor is failing or degraded, so an
 * admin learns "Sarvam is out of credits" here instead of from a tenant ticket.
 */
export function ProviderHealthBanner() {
  const { data, reload } = useAdminResource<ProviderHealth>(PROVIDER_HEALTH_PATH);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void reload();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const items = data?.banner ?? [];
  if (!items.length) return null;
  const failing = items.some((i) => i.status === "failing");

  return (
    <div
      role={failing ? "alert" : "status"}
      className={
        failing
          ? "rounded-skeuo-md border border-status-error/30 bg-status-error/10 p-4 text-sm"
          : "rounded-skeuo-md border border-status-warning/30 bg-status-warning/10 p-4 text-sm"
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className={failing ? "font-semibold text-status-error" : "font-semibold text-text"}>
            {failing ? "A voice stack service is failing — calls may be rejected" : "A voice stack service is degraded"}
          </p>
          <ul className="space-y-0.5 text-text">
            {items.slice(0, 4).map((item) => (
              <li key={`${item.provider}-${item.component}`}>
                {item.headline}
                {item.since ? <span className="text-text-muted"> · started {relativeTime(item.since).toLowerCase()}</span> : null}
                {item.callsRejected ? (
                  <span className="text-text-muted"> · {item.callsRejected} call{item.callsRejected === 1 ? "" : "s"} rejected</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
        <Link
          href="/dev/admin/provider-health"
          className="shrink-0 rounded-lg border border-surface-border bg-surface-panel px-3 py-1 text-xs font-medium text-text hover:bg-surface-panel-raised"
        >
          Open provider health
        </Link>
      </div>
    </div>
  );
}
