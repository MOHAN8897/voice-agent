"use client";

import { TIER_META, TIER_ORDER, type TierName } from "@/lib/voice-tier-meta";
import { cn } from "@/lib/cn";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";

export function VoiceTierSelector({
  value,
  onChange,
  disabled,
}: {
  value: TierName;
  onChange?: (tier: TierName) => void;
  disabled?: boolean;
}) {
  return (
    <div className="skeuo-panel rounded-skeuo-lg border border-surface-border-subtle p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="label-caps text-text-subtle">Tier selector</p>
          <p className="mt-1 text-sm text-text-muted">Machined rotary positions — exactly three customer-facing tiers.</p>
        </div>
        <SkeuoBadge tone="accent">{TIER_META[value].label} active</SkeuoBadge>
      </div>

      <div className="mt-5 grid gap-2 sm:grid-cols-3">
        {TIER_ORDER.map((tier) => {
          const meta = TIER_META[tier];
          const active = value === tier;
          return (
            <button
              key={tier}
              type="button"
              disabled={disabled}
              onClick={() => onChange?.(tier)}
              className={cn(
                "group relative rounded-skeuo-md border px-4 py-4 text-left transition-all duration-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                active
                  ? "skeuo-nav-active border-accent-primary/30 text-text"
                  : "border-surface-border-subtle text-text-muted hover:border-accent-primary/20 hover:text-text skeuo-inset",
                disabled && "opacity-60 cursor-not-allowed"
              )}
              aria-pressed={active}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs uppercase tracking-[0.16em]">{meta.label}</span>
                {active && <span className="skeuo-led skeuo-led-ok" aria-hidden />}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-text-muted">{meta.description}</p>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-mono uppercase tracking-wider">
                <div className="skeuo-inset rounded-skeuo-sm px-2 py-1">
                  <dt className="text-text-subtle">Cost</dt>
                  <dd className="mt-0.5 text-text">{meta.cost}</dd>
                </div>
                <div className="skeuo-inset rounded-skeuo-sm px-2 py-1">
                  <dt className="text-text-subtle">Latency</dt>
                  <dd className="mt-0.5 text-text">{meta.latency}</dd>
                </div>
                <div className="skeuo-inset rounded-skeuo-sm px-2 py-1">
                  <dt className="text-text-subtle">Quality</dt>
                  <dd className="mt-0.5 text-text">{meta.quality}</dd>
                </div>
              </dl>
            </button>
          );
        })}
      </div>
    </div>
  );
}
