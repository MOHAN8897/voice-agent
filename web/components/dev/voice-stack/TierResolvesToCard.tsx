"use client";

import Link from "next/link";
import {
  PRICE_SOURCE_LABEL,
  StatusPill,
  blockerHint,
  formatInr,
  type TierProfileRow,
} from "@/components/dev/voice-stack/profileModel";

const KNOB_LABELS: Record<string, string> = {
  speed: "Pace",
  pitch: "Pitch",
  temperature: "Expressiveness",
  emotion: "Emotion",
  volume: "Volume",
};

function knobValue(value: number | string): string {
  return typeof value === "number" ? value.toFixed(2) : String(value);
}

/**
 * What a call on this tier will actually use, from the SAVED server record:
 * effective stages, voices, knobs after per-model clamping, price and source,
 * public/enabled state, and how to fix anything blocking readiness.
 */
export function TierResolvesToCard({
  row,
  agentCount,
  hasUnsavedChanges,
}: {
  row: TierProfileRow | undefined;
  agentCount: number | null;
  hasUnsavedChanges: boolean;
}) {
  const profile = row?.composedProfile;
  if (!row || !profile) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-muted" data-testid="tier-resolves-to">
        This tier has no saved setup yet. Load the recommended setup and save it.
      </div>
    );
  }
  const native = row.native === true || row.readiness.verificationPath === "test_studio";
  const enabled = row.readiness.enabled === true;
  const ready = row.readiness.ready === true;
  const voiceCount = (profile.engines || []).reduce(
    (total, engine) => total + (engine.models || []).reduce((sum, model) => sum + (model.voices?.length || 0), 0),
    0,
  );
  const webSource = row.webRetailRate?.source === "global_web_default" ? "Platform web default" : "Set on this tier card";

  return (
    <section
      aria-labelledby="tier-resolves-heading"
      data-testid="tier-resolves-to"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border-subtle pb-3">
        <div>
          <h3 id="tier-resolves-heading" className="text-sm font-semibold text-text">Resolves to (saved revision {row.profileRevision ?? 0})</h3>
          <p className="text-[11px] text-text-subtle">
            What a new call on this tier uses right now.{hasUnsavedChanges ? " Your unsaved edits are not included." : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={enabled ? "good" : "muted"}>{enabled ? "Enabled" : "Disabled"}</StatusPill>
          <StatusPill tone={row.public ? "good" : "muted"}>{row.public ? "Shown to tenants" : "Hidden from tenants"}</StatusPill>
          <StatusPill tone={ready ? "good" : enabled ? "bad" : "warn"}>{ready ? "Ready" : "Not ready"}</StatusPill>
          {agentCount !== null && (
            <span className="text-[11px] text-text-muted">{agentCount} agent{agentCount === 1 ? "" : "s"} on this tier</span>
          )}
        </div>
      </div>

      <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-text-subtle">Speech recognition</dt>
          <dd className="mt-0.5 font-mono text-text">
            {native ? "Built into the live model" : `${profile.stt.provider} / ${profile.stt.model}`}
          </dd>
        </div>
        <div>
          <dt className="text-text-subtle">Conversation model</dt>
          <dd className="mt-0.5 font-mono text-text">{profile.llm.provider} / {profile.llm.modelId}</dd>
          <dd className="text-[11px] text-text-subtle">{native ? "Native audio session" : `Transport: ${profile.llm.apiMode}`}</dd>
        </div>
        <div>
          <dt className="text-text-subtle">Speech output</dt>
          {(profile.engines || []).flatMap((engine) => (engine.models || []).map((model) => (
            <dd key={`${engine.id}-${model.id}`} className="mt-0.5 font-mono text-text">
              {model.provider} / {model.model}
            </dd>
          )))}
          <dd className="text-[11px] text-text-subtle">{voiceCount} approved voice{voiceCount === 1 ? "" : "s"} · {profile.supportedLanguages.length} language{profile.supportedLanguages.length === 1 ? "" : "s"}</dd>
        </div>
        <div>
          <dt className="text-text-subtle">Phone call price</dt>
          <dd className="mt-0.5 font-mono text-text">{formatInr(row.retailRate?.inrPaisePerMin)}</dd>
          <dd className="text-[11px] text-text-subtle">{PRICE_SOURCE_LABEL[row.priceSource || "missing"] || row.priceSource}</dd>
          <dd className="mt-1 font-mono text-text">Web: {formatInr(row.webRetailRate?.inrPaisePerMin)}</dd>
          <dd className="text-[11px] text-text-subtle">{row.webRetailRate ? webSource : "No web price"}</dd>
        </div>
      </dl>

      <div className="mt-4">
        <h4 className="text-xs font-semibold text-text">Voice knobs as each speech model receives them</h4>
        {(row.effectiveVoiceDynamics || []).length === 0 ? (
          <p className="mt-1 text-[11px] text-text-subtle">No tier knobs saved; each model uses its own defaults.</p>
        ) : (
          <ul className="mt-1 space-y-1.5">
            {(row.effectiveVoiceDynamics || []).map((item) => {
              const applied = Object.entries(item.applied || {});
              return (
                <li key={`${item.engineId}-${item.modelId}`} className="rounded-lg border border-surface-border-subtle bg-surface-panel px-3 py-2 text-[11px]">
                  <span className="font-mono text-text">{item.provider} / {item.model}</span>
                  <span className="text-text-muted">
                    {" · "}
                    {applied.length
                      ? applied.map(([key, value]) => `${KNOB_LABELS[key] || key} ${knobValue(value)}`).join(", ")
                      : "no knobs applied"}
                  </span>
                  {item.ignored.length > 0 && (
                    <span className="block text-amber-300">
                      Not supported by this model, so not sent: {item.ignored.map((key) => KNOB_LABELS[key] || key).join(", ")}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {(row.readiness.disabledReason || profile.disabledReason) && !enabled && (
        <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          Offline: {(row.readiness.disabledReason || profile.disabledReason)?.message}
        </p>
      )}

      {row.readiness.blockers.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold text-text">What blocks readiness</h4>
          <ul className="mt-1 space-y-1.5 text-xs">
            {row.readiness.blockers.map((blocker) => (
              <li key={blocker.code} className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2">
                <span className="text-amber-200">{blocker.message}</span>
                <span className="block text-[11px] text-text-muted">How to fix: {blockerHint(blocker.code, native)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {native && (
        <p className="mt-4 text-[11px] text-text-muted">
          Native audio tiers skip the synthetic stage checks: one live model listens, reasons and speaks. Confirm call quality in{" "}
          <Link href="/dev/test-studio" className="font-semibold text-accent underline-offset-2 hover:underline">Test Studio</Link>{" "}
          before enabling the tier.
        </p>
      )}
    </section>
  );
}
