"use client";

import { useEffect, useState } from "react";
import { AdminError, AdminLoading, AdminPageHeader } from "@/components/admin/AdminNav";
import { relativeTime, type BadgeTone } from "@/components/admin/accounts/model";
import { EmptyState, KeyValues, Notice, StatusBadge } from "@/components/admin/accounts/ui";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";
import {
  PROVIDER_HEALTH_PATH,
  type HealthStatus,
  type Incident,
  type KeyPool,
  type ProviderCard,
  type ProviderHealth,
} from "@/components/admin/health/types";

const STATUS_LABEL: Record<HealthStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  failing: "Failing",
  not_configured: "Not configured",
};

const STATUS_TONE: Record<HealthStatus, BadgeTone> = {
  healthy: "success",
  degraded: "warning",
  failing: "error",
  not_configured: "muted",
};

const SLOT_LABEL = (slot: string) => (slot === "primary" ? "Primary key" : `Backup key ${slot.replace("secondary-", "")}`);

const SLOT_STATE: Record<string, { label: string; tone: BadgeTone }> = {
  active: { label: "In use", tone: "success" },
  standby: { label: "Standby", tone: "muted" },
  cooling_down: { label: "Rejected — cooling down", tone: "error" },
};

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function KeySlots({ pool, categories }: { pool: KeyPool; categories: Record<string, string> }) {
  if (!pool.slots.length) {
    return <Notice tone="error">No Sarvam API key is configured. Add SARVAM_API_KEY (and optional SARVAM_API_KEY_1…) to the environment.</Notice>;
  }
  return (
    <ul className="space-y-1.5">
      {pool.slots.map((slot) => {
        const state = SLOT_STATE[slot.state] ?? SLOT_STATE.standby;
        return (
          <li key={slot.slot} className="flex flex-wrap items-center justify-between gap-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel px-2.5 py-1.5 text-xs">
            <span className="font-medium text-text">{SLOT_LABEL(slot.slot)}</span>
            <span className="flex flex-wrap items-center gap-2 text-text-muted">
              {slot.category ? <span>{categories[slot.category] ?? slot.category}</span> : null}
              {slot.state === "cooling_down" && slot.retryInSeconds > 0 ? (
                <span>re-check in {Math.ceil(slot.retryInSeconds / 60)} min</span>
              ) : null}
              <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Card({
  card,
  categories,
  busy,
  onResolve,
  onRecheck,
}: {
  card: ProviderCard;
  categories: Record<string, string>;
  busy: string;
  onResolve: (ids: string[]) => void;
  onRecheck: () => void;
}) {
  const problem = card.status === "failing" || card.status === "degraded";
  const border =
    card.status === "failing"
      ? "border-status-error/40"
      : card.status === "degraded"
        ? "border-status-warning/40"
        : "border-surface-border-subtle";
  return (
    <article className={`card-surface flex min-w-0 flex-col gap-3 border p-4 ${border}`}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-text">{card.label}</h3>
          {card.keys ? (
            <p className="text-[11px] text-text-subtle">
              {card.keys.activeSlot ? `Using: ${SLOT_LABEL(card.keys.activeSlot).toLowerCase()}` : "No usable key right now"}
            </p>
          ) : null}
        </div>
        <StatusBadge tone={STATUS_TONE[card.status]}>{STATUS_LABEL[card.status]}</StatusBadge>
      </header>

      <p className={`text-sm ${card.status === "failing" ? "text-status-error" : problem ? "text-text" : "text-text-muted"}`}>
        {card.headline}
      </p>

      {problem ? (
        <KeyValues
          items={[
            ["Started", card.since ? relativeTime(card.since) : "—"],
            ["Last error", card.lastSeen ? relativeTime(card.lastSeen) : "—"],
            ["Errors", card.count.toLocaleString()],
            ["Calls affected", `${card.callsAffected}${card.callsRejected ? ` (${card.callsRejected} rejected)` : ""}`],
            ["Tenants affected", String(card.tenantsAffected)],
            ["Reason", card.categoryLabel ?? "—"],
          ]}
        />
      ) : null}

      {card.detail && problem ? <p className="break-words font-mono text-[11px] text-text-subtle">{card.detail}</p> : null}
      {!problem && card.recentlyRecovered ? <Notice tone="success">{card.recentlyRecovered}</Notice> : null}
      {card.keys ? <KeySlots pool={card.keys} categories={categories} /> : null}

      <footer className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        {card.billingUrl ? (
          <a
            href={card.billingUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-text hover:bg-surface-panel-raised"
          >
            Open {card.label} console
          </a>
        ) : null}
        {card.keys ? (
          <button
            type="button"
            disabled={busy === "recheck"}
            onClick={onRecheck}
            className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-text hover:bg-surface-panel-raised disabled:opacity-50"
            title="Sends one tiny request with each key and updates which key is used"
          >
            {busy === "recheck" ? "Checking keys…" : "Re-check keys now"}
          </button>
        ) : null}
        {card.incidentIds.length ? (
          <button
            type="button"
            disabled={busy === card.incidentIds.join(",")}
            onClick={() => onResolve(card.incidentIds)}
            className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-text-muted hover:text-text disabled:opacity-50"
            title="Hide this incident until it happens again"
          >
            Mark resolved
          </button>
        ) : null}
      </footer>
    </article>
  );
}

function IncidentRow({ incident, categories }: { incident: Incident; categories: Record<string, string> }) {
  const tone: BadgeTone = incident.active ? (incident.allKeysFailed ? "error" : "warning") : "muted";
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 border-b border-surface-border-subtle py-2 text-xs last:border-0">
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm text-text">{incident.message}</p>
        <p className="text-text-subtle">
          {incident.component.toUpperCase()} · {categories[incident.category] ?? incident.category}
          {incident.status ? ` · HTTP ${incident.status}` : ""} · {plural(incident.count, "error")}
          {incident.callsAffected ? ` · ${plural(incident.callsAffected, "call")}` : ""}
          {incident.tenantsAffected ? ` · ${plural(incident.tenantsAffected, "tenant")}` : ""}
        </p>
        <p className="text-text-subtle">
          {formatWhen(incident.firstSeen)} → {formatWhen(incident.lastSeen)}
        </p>
      </div>
      <StatusBadge tone={tone}>{incident.active ? "Active" : incident.acknowledgedAt ? "Marked resolved" : incident.resolvedAt ? "Recovered" : "Quiet"}</StatusBadge>
    </li>
  );
}

export function ProviderHealthWorkspace() {
  const { data, error, loading, reload } = useAdminResource<ProviderHealth>(PROVIDER_HEALTH_PATH);
  const [view, setView] = useState<ProviderHealth | null>(null);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [recheckNote, setRecheckNote] = useState<string | null>(null);

  useEffect(() => {
    if (data) setView(data);
  }, [data]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void reload();
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  async function resolve(ids: string[]) {
    setBusy(ids.join(","));
    setActionError(null);
    try {
      let next: ProviderHealth | null = null;
      for (const id of ids) {
        next = await adminAction<ProviderHealth>(`${PROVIDER_HEALTH_PATH}/incidents/${encodeURIComponent(id)}/resolve`);
      }
      if (next) setView(next);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not update the incident");
    } finally {
      setBusy("");
    }
  }

  async function recheck() {
    setBusy("recheck");
    setActionError(null);
    try {
      const next = await adminAction<ProviderHealth>(`${PROVIDER_HEALTH_PATH}/sarvam/recheck`);
      setView(next);
      const parts = (next.recheck ?? []).map(
        (r) => `${SLOT_LABEL(r.slot)}: ${r.ok ? "working" : (r.category && next.categories[r.category]) || `HTTP ${r.status ?? "error"}`}`
      );
      setRecheckNote(parts.length ? parts.join(" · ") : "No Sarvam keys configured.");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Re-check failed");
    } finally {
      setBusy("");
    }
  }

  const health = view;
  const categories = health?.categories ?? {};
  const failing = health?.banner.filter((b) => b.status === "failing") ?? [];

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Provider health"
        description="Every service the voice agent depends on, and whether it is working. Errors come from real calls and requests: out of credits, quota, rejected keys, outages and timeouts. Keys are never shown."
        actions={
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className="rounded-lg border border-surface-border px-3 py-1 text-xs disabled:opacity-50"
          >
            Refresh
          </button>
        }
      />
      <AdminError error={error} />
      <AdminError error={actionError} />
      <AdminLoading loading={loading && !health} />
      {recheckNote ? <Notice tone="info">Key re-check: {recheckNote}</Notice> : null}

      {health ? (
        <>
          {failing.length ? (
            <Notice tone="error">
              {failing.length === 1 ? "One service is failing" : `${failing.length} services are failing`}: calls that need{" "}
              {failing.map((f) => f.label).filter((v, i, a) => a.indexOf(v) === i).join(", ")} are being rejected or will fail. Tenants see
              “the voice service is temporarily unavailable” and are not charged.
            </Notice>
          ) : health.overall === "degraded" ? (
            <Notice tone="warning">Some services are degraded but calls are still going through.</Notice>
          ) : (
            <Notice tone="success">All configured services are healthy. Checked {relativeTime(health.checkedAt).toLowerCase()}.</Notice>
          )}

          {health.components.map((group) => (
            <section key={group.component} className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-subtle">{group.label}</h2>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {group.providers.map((card) => (
                  <Card
                    key={`${card.component}-${card.provider}`}
                    card={card}
                    categories={categories}
                    busy={busy}
                    onResolve={(ids) => void resolve(ids)}
                    onRecheck={() => void recheck()}
                  />
                ))}
              </div>
            </section>
          ))}

          <section className="card-surface p-4">
            <h2 className="mb-2 font-semibold text-text">Recent incidents</h2>
            {health.incidents.length ? (
              <ul>
                {health.incidents.slice(0, 50).map((incident) => (
                  <IncidentRow key={incident.id} incident={incident} categories={categories} />
                ))}
              </ul>
            ) : (
              <EmptyState title="No provider errors recorded" body="Failures from any stack service will appear here as they happen, one line per outage." />
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
