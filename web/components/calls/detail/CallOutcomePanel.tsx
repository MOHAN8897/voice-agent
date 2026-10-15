"use client";

import { useEffect, useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";
import type { CallAnalyticsData, OutcomePayload } from "@/lib/call-detail-types";

type SyncResult = {
  ok: boolean;
  synced: boolean;
  message: string;
  destinations?: Array<{
    app: string;
    status: string;
    contact_id?: string;
    lead_id?: string;
    details?: string;
  }>;
  contact?: Record<string, unknown>;
};

export function CallOutcomePanel({
  outcome,
  callId,
}: {
  outcome: OutcomePayload | null;
  callId?: string;
}) {
  const [analytics, setAnalytics] = useState<CallAnalyticsData | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    if (!callId) return;
    let cancelled = false;
    setLoadingAnalytics(true);
    setSyncResult(null);

    fetch(`/api/call/${encodeURIComponent(callId)}/analytics`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((res) => {
        if (!cancelled && res?.analytics) {
          setAnalytics(res.analytics as CallAnalyticsData);
        }
      })
      .catch(() => {
        /* fallback to outcome payload */
      })
      .finally(() => {
        if (!cancelled) setLoadingAnalytics(false);
      });

    return () => {
      cancelled = true;
    };
  }, [callId]);

  const facts = outcome?.facts || outcome?.extracted_fields || analytics?.facts || {};
  const sentiment = analytics?.sentiment || (outcome?.disposition && ["converted", "site_visit_planned", "qualified", "interested"].includes(outcome.disposition) ? "positive" : outcome?.disposition === "not_interested" ? "negative" : "neutral");
  const sentimentLabel = analytics?.sentiment_label || (sentiment === "positive" ? "Positive (High Intent)" : sentiment === "negative" ? "Challenging / Negative" : "Neutral / General");
  const resolutionStatus = analytics?.resolution_status || (outcome?.disposition && ["converted", "site_visit_planned", "qualified"].includes(outcome.disposition) ? "resolved" : outcome?.next_action ? "action_required" : "inconclusive");

  async function handleSyncCrm() {
    if (!callId) return;
    setSyncing(true);
    try {
      const res = await fetch(`/api/call/${encodeURIComponent(callId)}/crm-sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      });
      const data = (await res.json()) as SyncResult;
      setSyncResult(data);
    } catch {
      setSyncResult({
        ok: false,
        synced: false,
        message: "Network error occurred while syncing to CRM.",
      });
    } finally {
      setSyncing(false);
    }
  }

  function handleDownloadExport(format: "vcf" | "csv") {
    if (!callId) return;
    const url = `/api/call/${encodeURIComponent(callId)}/crm-export?format=${format}`;
    window.open(url, "_blank", "noopener,noreferrer");
    setExportOpen(false);
  }

  async function handleCopyJson() {
    if (!callId) return;
    try {
      const res = await fetch(`/api/call/${encodeURIComponent(callId)}/crm-export?format=json`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error();
      const json = await res.json();
      await navigator.clipboard.writeText(JSON.stringify(json.contact ?? json, null, 2));
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
      setExportOpen(false);
    } catch {
      /* clipboard error */
    }
  }

  const sentimentTone =
    sentiment === "positive"
      ? "bg-emerald-500/15 text-emerald-600 border-emerald-500/30"
      : sentiment === "negative"
        ? "bg-rose-500/15 text-rose-600 border-rose-500/30"
        : "bg-sky-500/15 text-sky-600 border-sky-500/30";

  const talkTime = analytics?.talk_time;

  return (
    <SkeuoPanel
      title="Post-Call Analytics & CRM Sync"
      description="Conversation intelligence, disposition analytics, and automated CRM contact integration"
      padding="md"
    >
      {!outcome && !analytics ? (
        <p className="text-sm text-text-muted">Outcome pending or not generated yet.</p>
      ) : (
        <div className="space-y-4">
          {/* Key Metric Strip */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Sentiment Pill */}
            <div className={cn("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wider", sentimentTone)}>
              <span className={cn("inline-block h-2 w-2 rounded-full", sentiment === "positive" ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : sentiment === "negative" ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]" : "bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.5)]")} />
              {sentimentLabel}
            </div>

            {/* Disposition & Confidence */}
            <SkeuoBadge tone="info">
              {outcome?.disposition || analytics?.disposition || "no_outcome"}
            </SkeuoBadge>

            {(outcome?.disposition_confidence ?? analytics?.disposition_confidence) != null && (
              <span className="font-mono text-[10px] text-text-subtle">
                confidence {(((outcome?.disposition_confidence ?? analytics?.disposition_confidence) || 0) * 100).toFixed(0)}%
              </span>
            )}

            {/* Resolution status badge */}
            <SkeuoBadge
              tone={
                resolutionStatus === "resolved"
                  ? "success"
                  : resolutionStatus === "action_required"
                    ? "warning"
                    : "muted"
              }
            >
              {resolutionStatus === "resolved"
                ? "Resolved"
                : resolutionStatus === "action_required"
                  ? "Action Required"
                  : resolutionStatus.replace("_", " ")}
            </SkeuoBadge>
          </div>

          {/* Talk Time Analytics Meter */}
          {talkTime && (
            <div className="skeuo-inset rounded-skeuo-sm p-3">
              <div className="flex justify-between items-center text-xs text-text-subtle mb-1.5">
                <span className="font-medium text-text">Talk-Time Distribution</span>
                <span className="font-mono text-[10px]">
                  Caller {Math.round(talkTime.user_ratio * 100)}% · Agent {Math.round(talkTime.agent_ratio * 100)}%
                </span>
              </div>
              <div className="h-2 w-full bg-surface-raised rounded-full overflow-hidden flex">
                <div
                  className="bg-accent-primary transition-all duration-300"
                  style={{ width: `${Math.round(talkTime.user_ratio * 100)}%` }}
                  title={`Caller: ${talkTime.user_words} words across ${talkTime.user_turns} turns`}
                />
                <div
                  className="bg-accent-primary/30 transition-all duration-300"
                  style={{ width: `${Math.round(talkTime.agent_ratio * 100)}%` }}
                  title={`Agent: ${talkTime.agent_words} words across ${talkTime.agent_turns} turns`}
                />
              </div>
              <div className="flex justify-between text-[10px] font-mono text-text-subtle mt-1">
                <span>{talkTime.user_turns} caller turns</span>
                <span>{talkTime.agent_turns} agent turns</span>
              </div>
            </div>
          )}

          {/* Status Tags */}
          {((outcome?.status_tags && outcome.status_tags.length > 0) || (analytics?.status_tags && analytics.status_tags.length > 0)) && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Status tags</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(outcome?.status_tags || analytics?.status_tags || []).map((tag) => (
                  <SkeuoBadge key={tag} tone="accent">
                    {tag.replaceAll(":", " · ")}
                  </SkeuoBadge>
                ))}
              </div>
            </div>
          )}

          {/* Executive Summary */}
          {(outcome?.summary_en || analytics?.summary_en) && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Summary</p>
              <p className="mt-1 text-sm leading-relaxed text-text">
                {outcome?.summary_en || analytics?.summary_en}
              </p>
            </div>
          )}

          {/* Next Action Box */}
          {(outcome?.next_action || analytics?.next_action) && (
            <div className="skeuo-inset rounded-skeuo-sm p-3 border-l-2 border-accent-primary">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary font-semibold">
                Agreed Next Action
              </p>
              <p className="mt-1 text-sm font-medium text-text">
                {outcome?.next_action || analytics?.next_action}
              </p>
            </div>
          )}

          {/* Captured Customer Facts & Profile Card */}
          {Object.keys(facts).length > 0 && (
            <div className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-base/50 p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle mb-2">
                Captured Customer Intelligence
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                {Object.entries(facts).map(([k, v]) => (
                  <div key={k} className="flex flex-col rounded bg-surface px-2 py-1.5 border border-surface-border-subtle/50">
                    <span className="font-mono text-[10px] text-text-subtle uppercase">{k.replace("_", " ")}</span>
                    <span className="font-medium text-text truncate mt-0.5">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Objections Captured */}
          {((outcome?.objections && outcome.objections.length > 0) || (analytics?.objections && analytics.objections.length > 0)) && (
            <div className="rounded-skeuo-sm border border-amber-500/20 bg-amber-500/5 p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-amber-600 font-semibold">
                Customer Objections Raised
              </p>
              <ul className="mt-1 list-disc pl-4 text-xs text-text-muted space-y-1">
                {(outcome?.objections || analytics?.objections || []).map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </div>
          )}

          {/* CRM Contact Sync & Export Action Bar */}
          {callId && (
            <div className="mt-5 pt-4 border-t border-surface-border-subtle space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle font-semibold">
                  CRM Integration & Lead Export
                </span>
                {copyFeedback && (
                  <span className="font-mono text-[10px] text-emerald-600 font-medium animate-pulse">
                    ✓ Contact JSON copied to clipboard
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <SkeuoButton
                  type="button"
                  variant="primary"
                  size="sm"
                  disabled={syncing}
                  onClick={() => void handleSyncCrm()}
                >
                  {syncing ? "Syncing..." : "Sync to CRM"}
                </SkeuoButton>

                <div className="relative inline-block">
                  <SkeuoButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setExportOpen((prev) => !prev)}
                  >
                    Export Contact ▾
                  </SkeuoButton>

                  {exportOpen && (
                    <div className="absolute left-0 bottom-full mb-1 z-20 w-52 rounded-skeuo-md border border-surface-border-subtle bg-surface-raised p-1 shadow-lg">
                      <button
                        type="button"
                        onClick={() => handleDownloadExport("vcf")}
                        className="w-full text-left px-3 py-1.5 text-xs text-text hover:bg-surface-base rounded font-medium flex items-center justify-between"
                      >
                        <span>Download vCard (.vcf)</span>
                        <span className="font-mono text-[10px] text-text-subtle">Contacts</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDownloadExport("csv")}
                        className="w-full text-left px-3 py-1.5 text-xs text-text hover:bg-surface-base rounded font-medium flex items-center justify-between"
                      >
                        <span>Download CSV</span>
                        <span className="font-mono text-[10px] text-text-subtle">Excel/CRM</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleCopyJson()}
                        className="w-full text-left px-3 py-1.5 text-xs text-text hover:bg-surface-base rounded font-medium flex items-center justify-between"
                      >
                        <span>Copy Contact JSON</span>
                        <span className="font-mono text-[10px] text-text-subtle">API</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Sync Feedback Message */}
              {syncResult && (
                <div
                  className={cn(
                    "rounded-skeuo-sm p-3 text-xs border transition-all",
                    syncResult.synced
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700"
                      : "bg-surface-raised border-surface-border-subtle text-text-muted"
                  )}
                >
                  <p className="font-medium">{syncResult.message}</p>
                  {syncResult.destinations && syncResult.destinations.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {syncResult.destinations.map((d, i) => (
                        <p key={i} className="font-mono text-[11px] text-emerald-800">
                          ✓ {d.app}: {d.details} {d.contact_id ? `(ID: ${d.contact_id})` : ""}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </SkeuoPanel>
  );
}
