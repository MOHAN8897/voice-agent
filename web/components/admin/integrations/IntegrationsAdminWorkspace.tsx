"use client";

import { useState } from "react";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import { AdminError, AdminLoading, AdminPageHeader } from "@/components/admin/AdminNav";
import { relativeTime, type BadgeTone } from "@/components/admin/accounts/model";
import { EmptyState, Notice, StatusBadge, TextInput } from "@/components/admin/accounts/ui";
import { adminAction, useAdminResource } from "@/lib/useAdminResource";

const BASE = "/api/dev/admin/integrations";

type Usage = { total: number; succeeded: number; failed: number; unknown: number; lastUsedAt: string | null };

type PlatformApp = {
  app: string;
  name: string;
  category: string | null;
  authType: string | null;
  timing: string | null;
  gatewayReady: boolean;
  enabled: boolean;
  note: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  overrides: { on: number; off: number };
  workspaces: { connected: number; needsReauth: number };
  usage: Usage;
};

type WorkspaceSummary = { tenantId: string; name: string; status: string | null; connectedApps: string[]; usage: Usage };

type Overview = { apps: PlatformApp[]; workspaces: WorkspaceSummary[]; usageDays: number; gatewayReachable?: boolean };

type TenantApp = {
  app: string;
  name: string;
  category: string | null;
  platformEnabled: boolean;
  override: boolean | null;
  overrideNote: string | null;
  effective: boolean;
  connection: "connected" | "needs_reauth" | "unverified" | "not_connected";
  account: string | null;
  connectedAt: string | null;
  setupMissing: string[];
  agentRules: Array<{ agent: string; enabled: boolean; timing: string }>;
  usage: Usage;
};

type TenantDetail = { tenant: { tenantId: string; name: string; status: string }; items: TenantApp[]; usageDays: number };

const CONNECTION: Record<TenantApp["connection"], { label: string; tone: BadgeTone }> = {
  connected: { label: "Connected", tone: "success" },
  needs_reauth: { label: "Reconnect needed", tone: "error" },
  unverified: { label: "Not verified", tone: "warning" },
  not_connected: { label: "Not connected", tone: "muted" },
};

function UsageCell({ usage }: { usage: Usage }) {
  if (!usage.total) return <span className="text-text-subtle">No use</span>;
  return (
    <span className="text-text-muted">
      <span className="font-medium text-text">{usage.total}</span> runs
      {usage.failed ? <span className="text-status-error"> · {usage.failed} failed</span> : null}
      {usage.unknown ? <span className="text-status-warning"> · {usage.unknown} unconfirmed</span> : null}
      {usage.lastUsedAt ? <span className="block text-[11px] text-text-subtle">last {relativeTime(usage.lastUsedAt).toLowerCase()}</span> : null}
    </span>
  );
}

type Pending =
  | { kind: "platform"; app: PlatformApp; enabled: boolean }
  | { kind: "override"; tenantId: string; tenantName: string; app: TenantApp; enabled: boolean | null };

export function IntegrationsAdminWorkspace() {
  const [tab, setTab] = useState<"apps" | "workspaces">("apps");
  const [tenantId, setTenantId] = useState<string>("");
  const [manualId, setManualId] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const overview = useAdminResource<Overview>(BASE);
  const detail = useAdminResource<TenantDetail>(tenantId ? `/api/dev/admin/tenants/${encodeURIComponent(tenantId)}/integrations` : null);

  async function confirm(statement: string) {
    if (!pending) return;
    setBusy(true);
    setActionError(null);
    try {
      if (pending.kind === "platform") {
        await adminAction(`${BASE}/${pending.app.app}`, { method: "PUT", body: { enabled: pending.enabled, note: statement } });
      } else {
        await adminAction(`/api/dev/admin/tenants/${encodeURIComponent(pending.tenantId)}/integrations/${pending.app.app}`, {
          method: "PUT",
          body: { enabled: pending.enabled, note: statement },
        });
        await detail.reload();
      }
      await overview.reload();
      setPending(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not save the change");
    } finally {
      setBusy(false);
    }
  }

  const data = overview.data;
  const offCount = data?.apps.filter((a) => !a.enabled).length ?? 0;

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Integrations"
        description="Choose which apps workspaces can connect and their agents can use, for everyone or one workspace, and see each workspace's connections and usage. Switching an app off stops agents using it at once, even where it is already connected."
        actions={
          <button type="button" onClick={() => void overview.reload()} disabled={overview.loading}
            className="rounded-lg border border-surface-border px-3 py-1 text-xs disabled:opacity-50">
            Refresh
          </button>
        }
      />
      <AdminError error={overview.error} />
      <AdminError error={actionError} />
      <AdminLoading loading={overview.loading && !data} />

      <div role="tablist" className="flex gap-2">
        {([["apps", "All apps"], ["workspaces", "Workspaces"]] as const).map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${tab === key ? "border-accent bg-accent/10 text-text" : "border-surface-border text-text-muted"}`}>
            {label}
          </button>
        ))}
      </div>

      {data && tab === "apps" ? (
        <section className="card-surface overflow-x-auto p-0" data-testid="admin-integrations-apps">
          {data.gatewayReachable === false ? (
            <div className="p-3"><Notice tone="error">The integrations gateway (Nango) cannot be reached, so every app shows as not configured and workspaces cannot connect or use any app. Check that its server is running.</Notice></div>
          ) : null}
          {offCount ? <div className="p-3"><Notice tone="warning">{offCount} app{offCount === 1 ? " is" : "s are"} switched off for every workspace (except where a workspace override turns it on).</Notice></div> : null}
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="border-b border-surface-border-subtle text-[11px] uppercase tracking-wider text-text-subtle">
              <tr>
                <th className="px-3 py-2">App</th>
                <th className="px-3 py-2">Gateway</th>
                <th className="px-3 py-2">Workspaces</th>
                <th className="px-3 py-2">Last {data.usageDays} days</th>
                <th className="px-3 py-2">Available to workspaces</th>
              </tr>
            </thead>
            <tbody>
              {data.apps.map((app) => (
                <tr key={app.app} className="border-b border-surface-border-subtle align-top" data-testid={`admin-integration-${app.app.toLowerCase()}`}>
                  <td className="px-3 py-2">
                    <span className="font-medium text-text">{app.name}</span>
                    <span className="block text-[11px] text-text-subtle">
                      {app.category} · {app.authType === "oauth" ? "Sign in" : "API key"} · {app.timing === "in_call" ? "During calls" : "After calls"}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {app.gatewayReady ? <StatusBadge tone="success">Configured</StatusBadge> : <StatusBadge tone="error">Not configured</StatusBadge>}
                  </td>
                  <td className="px-3 py-2 text-text-muted">
                    {app.workspaces.connected} connected
                    {app.workspaces.needsReauth ? <span className="block text-status-error">{app.workspaces.needsReauth} need reconnecting</span> : null}
                    {app.overrides.on || app.overrides.off ? (
                      <span className="block text-[11px] text-text-subtle">overrides: {app.overrides.on} on · {app.overrides.off} off</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2"><UsageCell usage={app.usage} /></td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={app.enabled ? "success" : "muted"}>{app.enabled ? "On" : "Off"}</StatusBadge>
                      <button type="button" onClick={() => setPending({ kind: "platform", app, enabled: !app.enabled })}
                        data-testid={`admin-integration-toggle-${app.app.toLowerCase()}`}
                        className="rounded-lg border border-surface-border px-2 py-0.5 text-[11px]">
                        {app.enabled ? "Turn off" : "Turn on"}
                      </button>
                    </div>
                    {app.note ? <span className="mt-1 block text-[11px] text-text-subtle">“{app.note}”{app.updatedBy ? ` — ${app.updatedBy}` : ""}</span> : null}
                    {!app.gatewayReady && app.enabled ? (
                      <span className="mt-1 block text-[11px] text-status-warning">Workspaces see it as “Not available yet”: add this app’s sign-in credentials (client ID and secret) to the gateway first.</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {data && tab === "workspaces" ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
          <section className="card-surface space-y-2 p-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-text-subtle">Workspaces with integrations</h2>
            {data.workspaces.length ? (
              <ul className="space-y-1">
                {data.workspaces.map((w) => (
                  <li key={w.tenantId}>
                    <button type="button" onClick={() => setTenantId(w.tenantId)}
                      className={`w-full rounded-skeuo-sm border px-2.5 py-1.5 text-left text-xs ${tenantId === w.tenantId ? "border-accent bg-accent/10" : "border-surface-border-subtle"}`}>
                      <span className="font-medium text-text">{w.name}</span>
                      <span className="block text-text-muted">{w.connectedApps.length} connected · {w.usage.total} runs{w.usage.failed ? ` · ${w.usage.failed} failed` : ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No workspace has connected an app" body="Workspaces appear here once they connect an integration or run one on a call." />
            )}
            <form className="flex gap-2 pt-2" onSubmit={(e) => { e.preventDefault(); if (manualId.trim()) setTenantId(manualId.trim()); }}>
              <TextInput placeholder="Open by workspace ID" value={manualId} onChange={(e) => setManualId(e.target.value)} aria-label="Workspace ID" />
              <button type="submit" className="rounded-lg border border-surface-border px-3 py-1 text-xs">Open</button>
            </form>
          </section>

          <section className="card-surface overflow-x-auto p-0">
            {!tenantId ? (
              <div className="p-4"><EmptyState title="Choose a workspace" body="See its connections, setup, which agents use each app, and what ran on its calls." /></div>
            ) : (
              <>
                <AdminError error={detail.error} />
                <AdminLoading loading={detail.loading && !detail.data} />
                {detail.data ? (
                  <div data-testid="admin-tenant-integrations">
                    <div className="border-b border-surface-border-subtle p-3">
                      <h2 className="font-semibold text-text">{detail.data.tenant.name}</h2>
                      <p className="text-[11px] text-text-subtle">{detail.data.tenant.tenantId} · {detail.data.tenant.status}</p>
                    </div>
                    <table className="w-full min-w-[760px] text-left text-xs">
                      <thead className="border-b border-surface-border-subtle text-[11px] uppercase tracking-wider text-text-subtle">
                        <tr>
                          <th className="px-3 py-2">App</th>
                          <th className="px-3 py-2">Connection</th>
                          <th className="px-3 py-2">Agents</th>
                          <th className="px-3 py-2">Last {detail.data.usageDays} days</th>
                          <th className="px-3 py-2">Available here</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.data.items.map((item) => (
                          <tr key={item.app} className="border-b border-surface-border-subtle align-top" data-testid={`admin-tenant-integration-${item.app.toLowerCase()}`}>
                            <td className="px-3 py-2 font-medium text-text">{item.name}</td>
                            <td className="px-3 py-2">
                              <StatusBadge tone={CONNECTION[item.connection].tone}>{CONNECTION[item.connection].label}</StatusBadge>
                              {item.account ? <span className="mt-1 block text-[11px] text-text-subtle">{item.account}</span> : null}
                              {item.setupMissing.length ? <span className="mt-1 block text-[11px] text-status-warning">Needs setup: {item.setupMissing.join(", ")}</span> : null}
                            </td>
                            <td className="px-3 py-2 text-text-muted">
                              {item.agentRules.length
                                ? item.agentRules.map((r) => `${r.agent} (${r.enabled ? (r.timing === "in_call" ? "during" : "after") : "off"})`).join(", ")
                                : <span className="text-text-subtle">Defaults</span>}
                            </td>
                            <td className="px-3 py-2"><UsageCell usage={item.usage} /></td>
                            <td className="px-3 py-2">
                              <select
                                aria-label={`Availability of ${item.name} for this workspace`}
                                value={item.override === null ? "default" : item.override ? "on" : "off"}
                                onChange={(e) => {
                                  const v = e.target.value;
                                  setPending({ kind: "override", tenantId: detail.data!.tenant.tenantId, tenantName: detail.data!.tenant.name, app: item,
                                    enabled: v === "default" ? null : v === "on" });
                                }}
                                className="rounded-lg border border-surface-border bg-surface-panel px-2 py-1 text-xs"
                              >
                                <option value="default">Platform setting ({item.platformEnabled ? "on" : "off"})</option>
                                <option value="on">On for this workspace</option>
                                <option value="off">Off for this workspace</option>
                              </select>
                              <span className={`mt-1 block text-[11px] ${item.effective ? "text-status-success" : "text-text-subtle"}`}>
                                {item.effective ? "Available" : "Not available"}
                              </span>
                              {item.overrideNote ? <span className="block text-[11px] text-text-subtle">“{item.overrideNote}”</span> : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </div>
      ) : null}

      <AdminConfirmDialog
        open={Boolean(pending)}
        busy={busy}
        tone={pending && (pending.kind === "platform" ? !pending.enabled : pending.enabled === false) ? "danger" : "default"}
        title={
          !pending ? "" : pending.kind === "platform"
            ? `${pending.enabled ? "Turn on" : "Turn off"} ${pending.app.name} for every workspace?`
            : `${pending.enabled === null ? "Use the platform setting for" : pending.enabled ? "Turn on" : "Turn off"} ${pending.app.name} in ${pending.tenantName}?`
        }
        description={
          !pending ? undefined : (pending.kind === "platform" ? !pending.enabled : pending.enabled === false)
            ? "Agents stop using it on new and in-progress calls within 30 seconds. Existing connections are kept, so turning it back on restores them."
            : "Workspaces can connect it and their agents can use it."
        }
        confirmLabel="Save"
        onCancel={() => setPending(null)}
        onConfirm={(statement) => confirm(statement)}
      />
    </div>
  );
}
