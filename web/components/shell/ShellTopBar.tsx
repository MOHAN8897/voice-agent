"use client";

import Link from "next/link";
import { SkeuoStatusLight } from "@/components/ui/skeuo";
import { cn } from "@/lib/cn";

type Env = "development" | "staging" | "production";

const ENV_LABEL: Record<Env, string> = {
  development: "DEV",
  staging: "STAGING",
  production: "PRODUCTION",
};

export function ShellTopBar({
  productLabel,
  entityLabel,
  environment = "development",
  connectionStatus = "ok",
  tier,
  profileHref,
  profileLabel = "Account",
}: {
  productLabel: string;
  entityLabel?: React.ReactNode;
  environment?: Env;
  connectionStatus?: "ok" | "warn" | "error";
  tier?: string;
  profileHref?: string;
  profileLabel?: string;
}) {
  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-surface-border-subtle bg-surface-panel/40 px-4 py-3 md:px-6">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">{productLabel}</p>
        {entityLabel && <p className="truncate text-sm font-medium text-text">{entityLabel}</p>}
      </div>

      <div className="flex items-center gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-0.5">
        {(["development", "staging", "production"] as Env[]).map((env) => (
          <span
            key={env}
            className={cn(
              "rounded-skeuo-sm px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider border",
              env === environment
                ? env === "development"
                  ? "skeuo-env-dev"
                  : env === "staging"
                    ? "skeuo-env-staging"
                    : "skeuo-env-prod"
                : "border-transparent text-text-subtle opacity-50"
            )}
            aria-current={env === environment ? "true" : undefined}
          >
            {ENV_LABEL[env]}
          </span>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <SkeuoStatusLight
          status={connectionStatus === "ok" ? "ok" : connectionStatus === "warn" ? "warn" : "error"}
          label="API"
        />
        {tier && (
          <span className="rounded-skeuo-sm border border-surface-border-subtle px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-text-muted skeuo-inset">
            Tier {tier}
          </span>
        )}
        {profileHref && (
          <Link
            href={profileHref}
            className="rounded-skeuo-sm border border-surface-border-subtle px-3 py-1.5 text-xs font-medium text-text-muted skeuo-btn-secondary hover:text-text"
          >
            {profileLabel}
          </Link>
        )}
      </div>
    </header>
  );
}
