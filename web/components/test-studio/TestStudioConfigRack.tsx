"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { TIER_META, TIER_ORDER, type TierName } from "@/lib/voice-tier-meta";
import { cn } from "@/lib/cn";

type ChannelTab = "browser" | "pstn";

export function TestStudioConfigRack({
  channel,
  onChannelChange,
  showPstn,
  tier,
  onTierChange,
  language,
  onLanguageChange,
  sessionStatus,
  locked,
}: {
  channel: ChannelTab;
  onChannelChange: (c: ChannelTab) => void;
  showPstn?: boolean;
  tier: string;
  onTierChange: (t: string) => void;
  language: string;
  onLanguageChange: (l: string) => void;
  sessionStatus: string;
  locked: boolean;
}) {
  const tierKey = (tier.toLowerCase() as TierName) in TIER_META ? (tier.toLowerCase() as TierName) : "medium";

  return (
    <SkeuoPanel title="Configuration rack" description="Locks at call/start — production lifecycle" padding="md">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {(["browser", ...(showPstn ? ["pstn"] : [])] as ChannelTab[]).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => onChannelChange(c)}
              disabled={locked}
              className={cn(
                "rounded-skeuo-sm px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-all",
                channel === c ? "skeuo-btn-primary text-white" : "skeuo-btn-secondary",
                locked && "opacity-50"
              )}
            >
              {c === "browser" ? "Browser mic" : "PSTN · Plivo"}
            </button>
          ))}
        </div>

        <label className="block text-sm">
          <span className="text-text-muted">Tier</span>
          <select
            disabled={locked}
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
            value={tier}
            onChange={(e) => onTierChange(e.target.value)}
          >
            {TIER_ORDER.map((t) => (
              <option key={t} value={t}>{TIER_META[t].label}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="text-text-muted">Language</span>
          <select
            disabled={locked}
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
          >
            <option value="te-IN">te-IN — Telugu</option>
            <option value="en-IN">en-IN — English</option>
            <option value="hi-IN">hi-IN — Hindi</option>
          </select>
        </label>

        <div className="skeuo-inset rounded-skeuo-md p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">Session</span>
            <SkeuoBadge tone={locked ? "warning" : "info"}>{sessionStatus}</SkeuoBadge>
          </div>
          {locked && <p className="text-xs text-status-warning">Configuration locked during active call</p>}
        </div>
      </div>
    </SkeuoPanel>
  );
}
