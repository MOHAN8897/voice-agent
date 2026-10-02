"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AdminConfirmDialog } from "@/components/admin/AdminConfirmDialog";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import { DevCard } from "@/components/dev/DevCard";
import {
  SkeuoBadge,
  SkeuoButton,
  SkeuoInput,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type TabId = "overview" | "members" | "wallet" | "numbers" | "compliance" | "usage" | "audit";

type TenantDetail = {
  tenant: {
    tenantId: string;
    name: string;
    status: string;
    plan?: string | null;
    limits?: Record<string, unknown>;
    billingSource?: string | null;
    createdAt?: string | null;
  };
  wallet?: {
    balanceUsd?: number;
    balanceInr?: number;
    currency?: string;
    updatedAt?: string | null;
  } | null;
  walletTransactions?: Array<{
    id: string;
    kind: string;
    amountCents: number;
    amountInrPaise?: number;
    referenceId?: string | null;
    createdAt?: string | null;
  }>;
  verifications?: Array<{
    userId: string;
    email?: string | null;
    fullName?: string | null;
    status: string;
    approved: boolean;
    updatedAt?: string | null;
  }>;
  counts?: { agents?: number; numbers?: number; members?: number; calls?: number };
  agents: Array<{ agentId?: string; name: string; status?: string }>;
  numbers: Array<{ id?: string; e164: string; agentId?: string | null; status?: string }>;
  users?: Array<{ userId: string; email?: string; role: string; fullName?: string }>;
  members?: Array<{ userId: string; email?: string; role: string }>;
  recentCalls?: Array<{ callId: string; startedAt?: string | null; status?: string | null }>;
};

type ActivityPayload = {
  entries?: Array<{
    id?: string;
    action?: string;
    actor?: string;
    outcome?: string;
    createdAt?: string | null;
    summary?: string | null;
  }>;
};

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "members", label: "Members" },
  { id: "wallet", label: "Wallet" },
  { id: "numbers", label: "Numbers" },
  { id: "compliance", label: "Compliance" },
  { id: "usage", label: "Usage" },
  { id: "audit", label: "Audit" },
];

const PLANS = ["starter", "growth", "enterprise", "default", "dev"];
const STATUSES = ["active", "suspended", "past_due", "cancelled"];
const BILLING_SOURCES = ["self_serve", "manual", "enterprise"];

function numLimit(limits: Record<string, unknown> | undefined, key: string, fallback = 0): number {
  const v = limits?.[key];
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function boolFlag(limits: Record<string, unknown> | undefined, key: string): boolean {
  const features = limits?.features;
  if (features && typeof features === "object" && !Array.isArray(features)) {
    return Boolean((features as Record<string, unknown>)[key]);
  }
  return Boolean(limits?.[key]);
}

export default function TenantCockpitPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tenantId = String(params.tenantId || "");
  const tabParam = (searchParams.get("tab") || "overview") as TabId;
  const tab: TabId = TABS.some((t) => t.id === tabParam) ? tabParam : "overview";

  const detail = useAdminResource<TenantDetail>(
    tenantId ? `/api/dev/admin/tenants/${tenantId}` : null,
    [tenantId]
  );
  const audit = useAdminResource<ActivityPayload>(
    tenantId && tab === "audit"
      ? `/api/dev/admin/activity-log?tenantId=${encodeURIComponent(tenantId)}&limit=50`
      : null,
    [tenantId, tab]
  );

  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [plan, setPlan] = useState("starter");
  const [billingSource, setBillingSource] = useState("self_serve");
  const [maxNumbers, setMaxNumbers] = useState("5");
  const [maxAgents, setMaxAgents] = useState("10");
  const [maxCampaigns, setMaxCampaigns] = useState("3");
  const [featOutbound, setFeatOutbound] = useState(true);
  const [featWeb, setFeatWeb] = useState(true);
  const [featIntl, setFeatIntl] = useState(false);
  const [statusPending, setStatusPending] = useState<string | null>(null);
  const [releaseOnStatus, setReleaseOnStatus] = useState(false);
  const [revokeOnStatus, setRevokeOnStatus] = useState(true);
  const [impersonateOpen, setImpersonateOpen] = useState(false);
  const [teardownOpen, setTeardownOpen] = useState(false);
  const [walletUsd, setWalletUsd] = useState("10");
  const [walletNote, setWalletNote] = useState("");
  const [allocateE164, setAllocateE164] = useState("");

  useEffect(() => {
    const t = detail.data?.tenant;
    if (!t) return;
    setName(t.name || "");
    setPlan(t.plan || "starter");
    setBillingSource(t.billingSource || "self_serve");
    const lim = t.limits || {};
    setMaxNumbers(String(numLimit(lim, "max_numbers", 5)));
    setMaxAgents(String(numLimit(lim, "max_agents", 10)));
    setMaxCampaigns(String(numLimit(lim, "max_concurrent_campaigns", 3)));
    setFeatOutbound(boolFlag(lim, "outbound_campaigns") || lim.outbound_campaigns !== false);
    setFeatWeb(boolFlag(lim, "web_agent") || lim.web_agent !== false);
    setFeatIntl(boolFlag(lim, "international_dids"));
  }, [detail.data]);

  function setTab(next: TabId) {
    const p = new URLSearchParams(searchParams.toString());
    p.set("tab", next);
    router.replace(`/dev/admin/tenants/${tenantId}?${p.toString()}`);
  }

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy("");
    }
  }

  function saveConfig() {
    return run("save", async () => {
      await adminAction(`/api/dev/admin/tenants/${tenantId}`, {
        method: "PATCH",
        body: {
          name: name.trim(),
          plan,
          billingSource,
          limits: {
            max_numbers: Number(maxNumbers) || 0,
            max_agents: Number(maxAgents) || 0,
            max_concurrent_campaigns: Number(maxCampaigns) || 0,
            features: {
              outbound_campaigns: featOutbound,
              web_agent: featWeb,
              international_dids: featIntl,
            },
          },
          note: "Updated plan/limits from tenant cockpit",
        },
      });
      await detail.reload();
    });
  }

  function confirmStatus(statement: string) {
    if (!statusPending) return;
    return run(`status:${statusPending}`, async () => {
      await adminAction(`/api/dev/admin/tenants/${tenantId}`, {
        method: "PATCH",
        body: {
          status: statusPending,
          note: statement,
          releaseNumbers: releaseOnStatus,
          revokeSessions: revokeOnStatus,
        },
      });
      setStatusPending(null);
      setReleaseOnStatus(false);
      setRevokeOnStatus(true);
      await detail.reload();
    });
  }

  function confirmImpersonate(statement: string) {
    return run("impersonate", async () => {
      const res = await adminAction<{ url?: string }>("/api/dev/admin/tenants/" + tenantId + "/impersonate", {
        method: "POST",
        body: { note: statement, ttlMinutes: 30 },
      });
      setImpersonateOpen(false);
      if (res.url) {
        window.open(res.url, "_blank", "noopener,noreferrer");
      }
    });
  }

  function confirmTeardown(statement: string) {
    return run("teardown", async () => {
      await adminAction(`/api/dev/admin/tenants/${tenantId}`, {
        method: "PATCH",
        body: {
          status: "cancelled",
          note: statement,
          releaseNumbers: true,
          revokeSessions: true,
        },
      });
      await adminAction(`/api/dev/admin/tenants/${tenantId}?force=true`, { method: "DELETE" });
      setTeardownOpen(false);
      router.push("/dev/admin/tenants");
    });
  }

  function adjustWallet(sign: 1 | -1) {
    const dollars = Number(walletUsd);
    if (!Number.isFinite(dollars) || dollars <= 0) {
      setError("Enter a positive USD amount");
      return;
    }
    if (walletNote.trim().length < 8) {
      setError("Wallet adjustment requires an admin statement (min 8 chars)");
      return;
    }
    return run(sign > 0 ? "credit" : "debit", async () => {
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId,
          amountUsdCents: Math.round(dollars * 100) * sign,
          reason: sign > 0 ? "admin_credit" : "admin_debit",
          note: walletNote.trim(),
        },
      });
      setWalletNote("");
      await detail.reload();
    });
  }

  function allocateNumber() {
    const e164 = allocateE164.trim();
    if (!e164.startsWith("+")) {
      setError("E.164 required (e.g. +15551234567)");
      return;
    }
    return run("allocate", async () => {
      await adminAction("/api/dev/admin/numbers/allocate", {
        method: "POST",
        body: { e164, tenantId },
      });
      setAllocateE164("");
      await detail.reload();
    });
  }

  function releaseNumber(numberId: string, e164: string) {
    return run(`release:${e164}`, async () => {
      await adminAction(`/api/dev/admin/numbers/${numberId}/release`, {
        method: "POST",
        body: { note: `Released from tenant cockpit ${tenantId}` },
      });
      await detail.reload();
    });
  }

  const members = detail.data?.users?.length
    ? detail.data.users
    : detail.data?.members ?? [];
  const t = detail.data?.tenant;
  const counts = detail.data?.counts;

  const statusTone = useMemo(() => {
    const s = t?.status;
    if (s === "active") return "good" as const;
    if (s === "past_due" || s === "suspended") return "warn" as const;
    return "default" as const;
  }, [t?.status]);

  if (!tenantId) {
    return <p className="p-6 text-sm text-text-muted">Missing tenant id.</p>;
  }

  return (
    <div className="space-y-6 p-6" data-testid="tenant-cockpit">
      <AdminPageHeader
        title={t?.name || "Tenant"}
        description={
          <span className="font-mono text-xs text-text-subtle">{tenantId}</span>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Link href="/dev/admin/tenants">
              <SkeuoButton variant="ghost">All tenants</SkeuoButton>
            </Link>
            <SkeuoButton
              variant="primary"
              disabled={Boolean(busy) || !members.length}
              onClick={() => setImpersonateOpen(true)}
            >
              Open as customer
            </SkeuoButton>
            <Link href={`/dev/admin/users?tenantId=${tenantId}`}>
              <SkeuoButton variant="ghost">Users</SkeuoButton>
            </Link>
            <Link href={`/dev/admin/activity?tenantId=${tenantId}`}>
              <SkeuoButton variant="ghost">Activity</SkeuoButton>
            </Link>
          </div>
        }
      />

      <AdminError error={error || detail.error} />
      <AdminLoading loading={detail.loading && !detail.data} />

      {detail.data && t && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <AdminStat label="Status" value={t.status} tone={statusTone} />
            <AdminStat label="Plan" value={t.plan || "—"} />
            <AdminStat
              label="Wallet USD"
              value={`$${Number(detail.data.wallet?.balanceUsd ?? 0).toFixed(2)}`}
            />
            <AdminStat label="Numbers" value={counts?.numbers ?? detail.data.numbers.length} />
            <AdminStat label="Members" value={counts?.members ?? members.length} />
          </div>

          <div className="flex flex-wrap gap-1 border-b border-surface-border-subtle pb-2">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`rounded-skeuo-sm px-3 py-1.5 text-xs font-medium ${
                  tab === item.id
                    ? "bg-surface-panel-raised text-text"
                    : "text-text-muted hover:text-text"
                }`}
                data-testid={`tenant-tab-${item.id}`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <DevCard title="Plan & limits">
                <div className="space-y-3">
                  <label className="block text-xs">
                    <span className="text-text-muted">Name</span>
                    <SkeuoInput className="mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} />
                  </label>
                  <label className="block text-xs">
                    <span className="text-text-muted">Plan</span>
                    <select
                      value={plan}
                      onChange={(e) => setPlan(e.target.value)}
                      className="mt-1 block w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs"
                    >
                      {PLANS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs">
                    <span className="text-text-muted">Billing source</span>
                    <select
                      value={billingSource}
                      onChange={(e) => setBillingSource(e.target.value)}
                      className="mt-1 block w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1.5 text-xs"
                    >
                      {BILLING_SOURCES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    <label className="block text-xs">
                      <span className="text-text-muted">Max numbers</span>
                      <SkeuoInput
                        className="mt-1 w-full"
                        value={maxNumbers}
                        onChange={(e) => setMaxNumbers(e.target.value)}
                      />
                    </label>
                    <label className="block text-xs">
                      <span className="text-text-muted">Max agents</span>
                      <SkeuoInput
                        className="mt-1 w-full"
                        value={maxAgents}
                        onChange={(e) => setMaxAgents(e.target.value)}
                      />
                    </label>
                    <label className="block text-xs">
                      <span className="text-text-muted">Campaigns</span>
                      <SkeuoInput
                        className="mt-1 w-full"
                        value={maxCampaigns}
                        onChange={(e) => setMaxCampaigns(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="space-y-1 text-xs text-text-muted">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={featOutbound} onChange={(e) => setFeatOutbound(e.target.checked)} />
                      Outbound campaigns
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={featWeb} onChange={(e) => setFeatWeb(e.target.checked)} />
                      Web agent
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={featIntl} onChange={(e) => setFeatIntl(e.target.checked)} />
                      International DIDs
                    </label>
                  </div>
                  <SkeuoButton variant="primary" disabled={busy === "save"} onClick={() => saveConfig()}>
                    Save configuration
                  </SkeuoButton>
                </div>
              </DevCard>

              <DevCard title="Lifecycle">
                <p className="mb-3 text-xs text-text-muted">
                  Current: <SkeuoBadge>{t.status}</SkeuoBadge> · Created {formatWhen(t.createdAt ?? null)}
                </p>
                <p className="mb-3 text-xs text-text-muted">
                  Status changes require a written statement and a side-effects checklist (release DIDs,
                  revoke sessions). Suspend freezes the workspace for customer login.
                </p>
                <div className="flex flex-wrap gap-2">
                  {STATUSES.filter((s) => s !== t.status).map((s) => (
                    <SkeuoButton
                      key={s}
                      variant="ghost"
                      disabled={Boolean(busy)}
                      onClick={() => {
                        setReleaseOnStatus(s === "suspended" || s === "cancelled");
                        setRevokeOnStatus(s === "suspended" || s === "cancelled");
                        setStatusPending(s);
                      }}
                    >
                      Set {s}
                    </SkeuoButton>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <SkeuoButton
                    variant="ghost"
                    disabled={Boolean(busy)}
                    onClick={() => setTeardownOpen(true)}
                    className="text-status-error"
                  >
                    Guided teardown
                  </SkeuoButton>
                  <Link href={`/dev/admin/billing?tenantId=${tenantId}`}>
                    <SkeuoButton variant="ghost">Adjust on billing page</SkeuoButton>
                  </Link>
                  <Link href={`/dev/admin/numbers?tenantId=${tenantId}`}>
                    <SkeuoButton variant="ghost">Numbers inventory</SkeuoButton>
                  </Link>
                </div>
              </DevCard>
            </div>
          )}

          {tab === "members" && (
            <DevCard
              title="Members & roles"
              description="Invite or change roles from Users; this tab is the tenant lens."
              actions={
                <Link href={`/dev/admin/users?tenantId=${tenantId}`}>
                  <SkeuoButton variant="primary">Manage users</SkeuoButton>
                </Link>
              }
            >
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Email</SkeuoTh>
                  <SkeuoTh>Role</SkeuoTh>
                  <SkeuoTh>User id</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {members.map((m) => (
                    <SkeuoTableRow key={m.userId}>
                      <SkeuoTd>{m.email || "—"}</SkeuoTd>
                      <SkeuoTd>
                        <SkeuoBadge>{m.role}</SkeuoBadge>
                      </SkeuoTd>
                      <SkeuoTd className="font-mono text-[10px]">{m.userId}</SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {!members.length && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No members — workspace cannot be signed into.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          )}

          {tab === "wallet" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <DevCard title="Adjust wallet (USD)">
                <p className="mb-2 text-xs text-text-muted">
                  Balance ${Number(detail.data.wallet?.balanceUsd ?? 0).toFixed(2)} USD · ₹
                  {Number(detail.data.wallet?.balanceInr ?? 0).toFixed(2)}
                </p>
                <label className="block text-xs">
                  <span className="text-text-muted">Amount (USD)</span>
                  <SkeuoInput
                    className="mt-1 w-full"
                    value={walletUsd}
                    onChange={(e) => setWalletUsd(e.target.value)}
                  />
                </label>
                <label className="mt-2 block text-xs">
                  <span className="text-text-muted">Admin statement</span>
                  <SkeuoInput
                    className="mt-1 w-full"
                    value={walletNote}
                    onChange={(e) => setWalletNote(e.target.value)}
                    placeholder="Why credit/debit?"
                  />
                </label>
                <div className="mt-3 flex gap-2">
                  <SkeuoButton
                    variant="primary"
                    disabled={busy === "credit"}
                    onClick={() => adjustWallet(1)}
                  >
                    Credit
                  </SkeuoButton>
                  <SkeuoButton
                    variant="ghost"
                    disabled={busy === "debit"}
                    onClick={() => adjustWallet(-1)}
                  >
                    Debit
                  </SkeuoButton>
                </div>
              </DevCard>
              <DevCard title="Ledger">
                <SkeuoTable>
                  <SkeuoTableHead>
                    <SkeuoTh>When</SkeuoTh>
                    <SkeuoTh>Kind</SkeuoTh>
                    <SkeuoTh className="text-right">USD</SkeuoTh>
                  </SkeuoTableHead>
                  <SkeuoTableBody>
                    {(detail.data.walletTransactions ?? []).map((tx) => (
                      <SkeuoTableRow key={tx.id}>
                        <SkeuoTd className="text-xs">{formatWhen(tx.createdAt ?? null)}</SkeuoTd>
                        <SkeuoTd>
                          <SkeuoBadge>{tx.kind}</SkeuoBadge>
                        </SkeuoTd>
                        <SkeuoTd className="text-right font-mono text-xs">
                          {(tx.amountCents / 100).toFixed(2)}
                        </SkeuoTd>
                      </SkeuoTableRow>
                    ))}
                    {!(detail.data.walletTransactions ?? []).length && (
                      <SkeuoTableRow>
                        <SkeuoTd className="text-text-muted">No transactions yet.</SkeuoTd>
                      </SkeuoTableRow>
                    )}
                  </SkeuoTableBody>
                </SkeuoTable>
              </DevCard>
            </div>
          )}

          {tab === "numbers" && (
            <DevCard title="Phone numbers">
              <div className="mb-4 flex flex-wrap items-end gap-2">
                <label className="text-xs">
                  <span className="text-text-muted">Allocate E.164</span>
                  <SkeuoInput
                    className="mt-1"
                    value={allocateE164}
                    onChange={(e) => setAllocateE164(e.target.value)}
                    placeholder="+15551234567"
                  />
                </label>
                <SkeuoButton
                  variant="primary"
                  disabled={busy === "allocate"}
                  onClick={() => allocateNumber()}
                >
                  Allocate
                </SkeuoButton>
              </div>
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>E.164</SkeuoTh>
                  <SkeuoTh>Status</SkeuoTh>
                  <SkeuoTh className="text-right">Actions</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {detail.data.numbers.map((n) => (
                    <SkeuoTableRow key={n.id || n.e164}>
                      <SkeuoTd className="font-mono text-xs">{n.e164}</SkeuoTd>
                      <SkeuoTd>{n.status || "—"}</SkeuoTd>
                      <SkeuoTd className="text-right">
                        <SkeuoButton
                          variant="ghost"
                          disabled={!n.id || busy === `release:${n.e164}`}
                          onClick={() => n.id && releaseNumber(n.id, n.e164)}
                        >
                          Release to inventory
                        </SkeuoButton>
                      </SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {!detail.data.numbers.length && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No active numbers.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          )}

          {tab === "compliance" && (
            <DevCard
              title="KYC / compliance"
              description="Identity verification for members of this workspace."
              actions={
                <Link href="/dev/admin/verification">
                  <SkeuoButton variant="ghost">Verification queue</SkeuoButton>
                </Link>
              }
            >
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>User</SkeuoTh>
                  <SkeuoTh>Status</SkeuoTh>
                  <SkeuoTh>Updated</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {(detail.data.verifications ?? []).map((v) => (
                    <SkeuoTableRow key={v.userId}>
                      <SkeuoTd>
                        <div className="text-sm">{v.email || v.userId}</div>
                        <div className="text-xs text-text-muted">{v.fullName || "—"}</div>
                      </SkeuoTd>
                      <SkeuoTd>
                        <SkeuoBadge>{v.status}</SkeuoBadge>
                        {v.approved ? (
                          <span className="ml-2 text-[10px] uppercase text-status-success">gate pass</span>
                        ) : null}
                      </SkeuoTd>
                      <SkeuoTd className="text-xs">{formatWhen(v.updatedAt ?? null)}</SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {!(detail.data.verifications ?? []).length && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No members to show KYC for.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          )}

          {tab === "usage" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <DevCard title="Agents">
                <ul className="space-y-1 text-sm text-text-muted">
                  {detail.data.agents.map((a) => (
                    <li key={a.agentId}>
                      {a.name}
                      {a.status ? ` · ${a.status}` : ""}
                    </li>
                  ))}
                  {!detail.data.agents.length && <li>None.</li>}
                </ul>
              </DevCard>
              <DevCard title="Recent calls">
                <ul className="space-y-1 font-mono text-xs text-text-muted">
                  {(detail.data.recentCalls ?? []).map((c) => (
                    <li key={c.callId}>
                      {c.callId.slice(0, 8)}… · {formatWhen(c.startedAt ?? null)}
                      {c.status ? ` · ${c.status}` : ""}
                    </li>
                  ))}
                  {!(detail.data.recentCalls ?? []).length && <li>No recent calls.</li>}
                </ul>
                <p className="mt-3 text-xs text-text-muted">
                  Lifetime calls: {counts?.calls ?? "—"}
                </p>
              </DevCard>
            </div>
          )}

          {tab === "audit" && (
            <DevCard title="Audit log (this tenant)">
              <AdminError error={audit.error} />
              <AdminLoading loading={audit.loading && !audit.data} />
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>When</SkeuoTh>
                  <SkeuoTh>Action</SkeuoTh>
                  <SkeuoTh>Actor</SkeuoTh>
                  <SkeuoTh>Outcome</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {(audit.data?.entries ?? []).map((ev, i) => (
                    <SkeuoTableRow key={ev.id || String(i)}>
                      <SkeuoTd className="text-xs">{formatWhen(ev.createdAt ?? null)}</SkeuoTd>
                      <SkeuoTd className="text-xs">{ev.action || ev.summary || "—"}</SkeuoTd>
                      <SkeuoTd className="text-xs">{ev.actor || "—"}</SkeuoTd>
                      <SkeuoTd>
                        <SkeuoBadge>{ev.outcome || "—"}</SkeuoBadge>
                      </SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {!(audit.data?.entries ?? []).length && !audit.loading && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No audit events for this tenant yet.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
              <p className="mt-2 text-xs text-text-muted">
                Full browser:{" "}
                <Link className="underline" href={`/dev/admin/activity?tenantId=${tenantId}`}>
                  Activity log
                </Link>
              </p>
            </DevCard>
          )}
        </>
      )}

      <AdminConfirmDialog
        open={Boolean(statusPending)}
        title={`Set status to ${statusPending}?`}
        description="Confirm the blast radius before changing tenant lifecycle status."
        tone={statusPending === "cancelled" || statusPending === "suspended" ? "danger" : "default"}
        confirmLabel={`Set ${statusPending}`}
        busy={Boolean(busy.startsWith("status:"))}
        onCancel={() => {
          setStatusPending(null);
          setReleaseOnStatus(false);
          setRevokeOnStatus(true);
        }}
        onConfirm={confirmStatus}
      >
        {(statusPending === "suspended" || statusPending === "cancelled") && (
          <>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={releaseOnStatus}
                onChange={(e) => setReleaseOnStatus(e.target.checked)}
              />
              Release all DIDs to Platform inventory
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={revokeOnStatus}
                onChange={(e) => setRevokeOnStatus(e.target.checked)}
              />
              Revoke member refresh tokens (force logout)
            </label>
            <p>Wallet stays intact; status alone blocks PSTN/console for this workspace.</p>
          </>
        )}
      </AdminConfirmDialog>

      <AdminConfirmDialog
        open={impersonateOpen}
        title="Open as customer"
        description="Opens a 30-minute support session in the customer console as a tenant admin. Fully audited."
        confirmLabel="Start impersonation"
        busy={busy === "impersonate"}
        onCancel={() => setImpersonateOpen(false)}
        onConfirm={confirmImpersonate}
      />

      <AdminConfirmDialog
        open={teardownOpen}
        title="Guided teardown"
        description="Releases DIDs to inventory, revokes sessions, sets cancelled, then soft-deletes (archives) the workspace."
        tone="danger"
        confirmLabel="Release · cancel · archive"
        busy={busy === "teardown"}
        onCancel={() => setTeardownOpen(false)}
        onConfirm={confirmTeardown}
      >
        <p>This cannot be undone from the UI. Numbers return to Platform inventory.</p>
      </AdminConfirmDialog>
    </div>
  );
}
