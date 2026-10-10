"use client";

import { useState } from "react";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import { DevCard } from "@/components/dev/DevCard";
import {
  SkeuoBadge,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import { formatUsd, useAdminResource } from "@/lib/useAdminResource";

type ChannelStats = { calls: number; seconds: number };

type Analytics = {
  windowDays: number;
  totals: {
    calls: number;
    seconds: number;
    missedCalls: number;
    tenants: number;
    tenantsActive: number;
    users: number;
    activeNumbers: number;
    failedPurchases: number;
    walletBalanceCents: number;
  };
  callsByDay: Array<{ date: string; calls: number; seconds: number }>;
  callsByStatus: Record<string, number>;
  callsByDirection: Record<string, number>;
  callsByChannel?: Record<string, ChannelStats>;
  topUpsByDay: Array<{ date: string; cents: number; inrPaise: number }>;
  topTenantsByCalls: Array<{ name: string; calls: number }>;
};

const WINDOWS = [7, 30, 90] as const;

function formatMinutes(seconds: number) {
  if (!seconds) return "0m";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m ${s}s`;
}

function channelLabel(key: string) {
  const k = key.toLowerCase();
  if (k === "browser" || k === "web") return "Web agent";
  if (k === "pstn" || k === "phone" || k === "telnyx" || k === "vobiz") return "Phone (PSTN)";
  return key;
}

function CallsByDay({ series }: { series: Analytics["callsByDay"] }) {
  const max = Math.max(1, ...series.map((d) => d.calls));
  return (
    <div className="space-y-2">
      {series.length === 0 ? (
        <p className="text-sm text-text-muted">No call volume in this window.</p>
      ) : (
        series.map((d) => (
          <div key={d.date} className="flex items-center gap-3 text-xs">
            <span className="w-24 shrink-0 font-mono text-text-muted">{d.date}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-panel-raised">
              <div
                className="h-full rounded-full bg-accent-primary/80"
                style={{ width: `${Math.max(4, (d.calls / max) * 100)}%` }}
              />
            </div>
            <span className="w-16 text-right font-mono">{d.calls}</span>
            <span className="w-16 text-right text-text-muted">{formatMinutes(d.seconds)}</span>
          </div>
        ))
      )}
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState<number>(30);
  const { data, error, loading } = useAdminResource<Analytics>(
    `/api/dev/admin/analytics?days=${days}`,
    [days]
  );

  const channels = data?.callsByChannel ?? {};
  const web = channels.browser || channels.web || { calls: 0, seconds: 0 };
  const phoneEntries = Object.entries(channels).filter(([k]) => {
    const key = k.toLowerCase();
    return key !== "browser" && key !== "web";
  });
  const phone = phoneEntries.reduce(
    (acc, [, v]) => ({ calls: acc.calls + v.calls, seconds: acc.seconds + v.seconds }),
    { calls: 0, seconds: 0 }
  );

  return (
    <div className="space-y-6 p-6" data-testid="admin-analytics-page">
      <AdminPageHeader
        title="Web & analytics"
        description="Product usage across browser web-agent sessions and PSTN phone calls, plus wallet top-ups and tenant load."
        actions={
          <div className="flex items-center gap-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setDays(w)}
                className={`rounded-skeuo-sm px-3 py-1 text-xs font-medium transition-colors ${
                  days === w
                    ? "bg-accent-primary text-white"
                    : "bg-surface-panel-raised text-text-muted hover:text-text"
                }`}
              >
                {w}d
              </button>
            ))}
          </div>
        }
      />

      <AdminError error={error} />
      <AdminLoading loading={loading && !data} />

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <AdminStat
              label={`All calls (${days}d)`}
              value={data.totals.calls.toLocaleString()}
              hint={formatMinutes(data.totals.seconds)}
            />
            <AdminStat
              label="Web agent"
              value={web.calls.toLocaleString()}
              hint={formatMinutes(web.seconds)}
              tone="good"
            />
            <AdminStat
              label="Phone (PSTN)"
              value={phone.calls.toLocaleString()}
              hint={formatMinutes(phone.seconds)}
            />
            <AdminStat
              label="Missed"
              value={data.totals.missedCalls}
              tone={data.totals.missedCalls > 0 ? "warn" : "good"}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <AdminStat label="Active tenants" value={`${data.totals.tenantsActive}/${data.totals.tenants}`} />
            <AdminStat label="Users" value={data.totals.users} />
            <AdminStat label="Active numbers" value={data.totals.activeNumbers} />
            <AdminStat
              label="Wallet float"
              value={formatUsd(data.totals.walletBalanceCents)}
              hint="sum of USD cents across tenants"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <DevCard title="Channel mix" description="browser = Talk-to-AI / Live Mic; other channels are carrier PSTN.">
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Channel</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                  <SkeuoTh className="text-right">Talk time</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {Object.entries(channels).length === 0 ? (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No calls in this window.</SkeuoTd>
                    </SkeuoTableRow>
                  ) : (
                    Object.entries(channels)
                      .sort((a, b) => b[1].calls - a[1].calls)
                      .map(([ch, stats]) => (
                        <SkeuoTableRow key={ch}>
                          <SkeuoTd>
                            <SkeuoBadge tone={ch === "browser" || ch === "web" ? "info" : "muted"}>
                              {channelLabel(ch)}
                            </SkeuoBadge>
                          </SkeuoTd>
                          <SkeuoTd className="text-right font-mono">{stats.calls}</SkeuoTd>
                          <SkeuoTd className="text-right font-mono text-xs">
                            {formatMinutes(stats.seconds)}
                          </SkeuoTd>
                        </SkeuoTableRow>
                      ))
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>

            <DevCard title="Direction">
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Direction</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {Object.entries(data.callsByDirection)
                    .sort((a, b) => b[1] - a[1])
                    .map(([dir, count]) => (
                      <SkeuoTableRow key={dir}>
                        <SkeuoTd>{dir}</SkeuoTd>
                        <SkeuoTd className="text-right font-mono">{count}</SkeuoTd>
                      </SkeuoTableRow>
                    ))}
                  {Object.keys(data.callsByDirection).length === 0 && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No calls in this window.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          </div>

          <DevCard title={`Calls per day (${days}d)`}>
            <CallsByDay series={data.callsByDay} />
          </DevCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <DevCard title="Status breakdown">
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Status</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {Object.entries(data.callsByStatus)
                    .sort((a, b) => b[1] - a[1])
                    .map(([status, count]) => (
                      <SkeuoTableRow key={status}>
                        <SkeuoTd>
                          <SkeuoBadge tone={status === "missed" ? "warning" : "muted"}>{status}</SkeuoBadge>
                        </SkeuoTd>
                        <SkeuoTd className="text-right font-mono">{count}</SkeuoTd>
                      </SkeuoTableRow>
                    ))}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>

            <DevCard title="Busiest tenants">
              <SkeuoTable>
                <SkeuoTableHead>
                  <SkeuoTh>Tenant</SkeuoTh>
                  <SkeuoTh className="text-right">Calls</SkeuoTh>
                </SkeuoTableHead>
                <SkeuoTableBody>
                  {data.topTenantsByCalls.map((t) => (
                    <SkeuoTableRow key={t.name}>
                      <SkeuoTd>{t.name}</SkeuoTd>
                      <SkeuoTd className="text-right font-mono">{t.calls}</SkeuoTd>
                    </SkeuoTableRow>
                  ))}
                  {data.topTenantsByCalls.length === 0 && (
                    <SkeuoTableRow>
                      <SkeuoTd className="text-text-muted">No calls in this window.</SkeuoTd>
                    </SkeuoTableRow>
                  )}
                </SkeuoTableBody>
              </SkeuoTable>
            </DevCard>
          </div>

          <DevCard title="Wallet top-ups by day" description="Credits from Razorpay / deposits only (not admin grants).">
            <SkeuoTable>
              <SkeuoTableHead>
                <SkeuoTh>Date</SkeuoTh>
                <SkeuoTh className="text-right">USD</SkeuoTh>
                <SkeuoTh className="text-right">INR</SkeuoTh>
              </SkeuoTableHead>
              <SkeuoTableBody>
                {data.topUpsByDay.length === 0 ? (
                  <SkeuoTableRow>
                    <SkeuoTd className="text-text-muted">No top-ups in this window.</SkeuoTd>
                  </SkeuoTableRow>
                ) : (
                  data.topUpsByDay.map((d) => (
                    <SkeuoTableRow key={d.date}>
                      <SkeuoTd className="font-mono text-xs">{d.date}</SkeuoTd>
                      <SkeuoTd className="text-right font-mono">{formatUsd(d.cents)}</SkeuoTd>
                      <SkeuoTd className="text-right font-mono text-xs">
                        ₹≈ ₹{(d.inrPaise / 100).toFixed(2)}
                      </SkeuoTd>
                    </SkeuoTableRow>
                  ))
                )}
              </SkeuoTableBody>
            </SkeuoTable>
          </DevCard>
        </>
      )}
    </div>
  );
}
