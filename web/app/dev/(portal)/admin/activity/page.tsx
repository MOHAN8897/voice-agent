"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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

type Entry = {
  id: string;
  actor: string;
  action: string;
  resourceType: string;
  resourceId: string;
  payload: Record<string, unknown>;
  source: string;
  outcome: string;
  severity: string;
  requestId?: string | null;
  ip?: string | null;
  userAgent?: string | null;
  tenantId?: string | null;
  createdAt: string | null;
};

type Facet = { value: string; count: number };

type ActivityPage = {
  entries: Entry[];
  total: number;
  limit: number;
  offset: number;
  facets: { actions: Facet[]; actors: Facet[] };
};

type Failure = {
  id: string;
  action: string;
  actor: string;
  source: string;
  severity: string;
  resourceType: string;
  resourceId: string;
  error?: unknown;
  createdAt: string | null;
};

type Summary = {
  total: number;
  since: string;
  counts: { outcome: Record<string, number>; severity: Record<string, number>; source: Record<string, number> };
  recentFailures: Failure[];
};

const PAGE_SIZE = 50;

const SEVERITY_TONE: Record<string, "success" | "warning" | "danger" | "muted" | "info"> = {
  info: "muted",
  warning: "warning",
  error: "danger",
};

const RANGES = [
  { label: "Last hour", hours: 1 },
  { label: "Last 24 hours", hours: 24 },
  { label: "Last 7 days", hours: 24 * 7 },
  { label: "Last 30 days", hours: 24 * 30 },
  { label: "All time", hours: 0 },
];

/** Start of the window `hours` ago. "All time" means no lower bound. */
function sinceStamp(hours: number): string {
  if (!hours || hours <= 0) return "1970-01-01T00:00:00.000Z";
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

export default function AdminActivityPage() {
  const searchParams = useSearchParams();
  const [source, setSource] = useState("");
  const [outcome, setOutcome] = useState("");
  const [severity, setSeverity] = useState("");
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [tenantId, setTenantId] = useState(searchParams.get("tenantId") || "");
  const [search, setSearch] = useState("");
  const [range, setRange] = useState("24");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [noteState, setNoteState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [noteError, setNoteError] = useState<string | null>(null);

  // `deps` rebuilds the query string, so changing any filter resets paging —
  // otherwise you land on page 4 of a result set that now has one page.
  const qs = useMemo(() => {
    const p = new URLSearchParams();
    p.set("limit", String(PAGE_SIZE));
    p.set("offset", String(offset));
    if (source) p.set("source", source);
    if (outcome) p.set("outcome", outcome);
    if (severity) p.set("severity", severity);
    if (action) p.set("action", action);
    if (actor) p.set("actor", actor);
    if (tenantId.trim()) p.set("tenantId", tenantId.trim());
    if (search.trim()) p.set("search", search.trim());
    const hours = Number(range);
    if (hours > 0) {
      p.set("since", sinceStamp(hours));
    }
    return p.toString();
  }, [source, outcome, severity, action, actor, tenantId, search, range, offset]);

  // The window start is derived from the selected range, not recomputed each
  // render. An inline `new Date()` produced a new URL every render, and
  // useAdminResource refetches whenever the path changes — so each response
  // triggered another request and the page never stopped loading.
  //
  // Tracking the range itself (not the timestamp) makes the mount-time effect a
  // no-op: state is seeded from `range`, so setting it to the same value bails
  // out instead of causing one extra fetch.
  const [windowRange, setWindowRange] = useState(range);
  const windowStart = useMemo(() => sinceStamp(Number(windowRange || 24)), [windowRange]);
  useEffect(() => {
    setWindowRange(range);
  }, [range]);

  const log = useAdminResource<ActivityPage>(`/api/dev/admin/activity-log?${qs}`);
  const summary = useAdminResource<Summary>(
    `/api/dev/admin/activity-log/summary?since=${encodeURIComponent(windowStart)}`
  );

  const resetPage = useCallback(() => setOffset(0), []);
  useEffect(() => {
    resetPage();
  }, [source, outcome, severity, action, actor, tenantId, search, range, resetPage]);

  const entries = log.data?.entries ?? [];
  const total = log.data?.total ?? 0;
  const actions = log.data?.facets?.actions ?? [];
  const failures = summary.data?.recentFailures ?? [];
  const byOutcome = summary.data?.counts?.outcome ?? {};
  const bySeverity = summary.data?.counts?.severity ?? {};
  const errors = byOutcome.error ?? 0;
  const warnings = bySeverity.warning ?? 0;

  async function saveNote() {
    if (!note.trim()) return;
    setNoteState("saving");
    setNoteError(null);
    try {
      await adminAction("/api/dev/admin/activity-log", {
        method: "POST",
        body: { text: note.trim() },
      });
      setNote("");
      setNoteState("saved");
      await log.reload();
    } catch (e) {
      setNoteState("error");
      setNoteError(e instanceof Error ? e.message : "Could not save the note");
    }
  }

  return (
    <div className="space-y-6 p-6" data-testid="admin-activity-page">
      <AdminPageHeader
        title="Activity log"
        description="Every recorded action across admin, subscriber, webhook and system sources. Filter to what failed when something looks wrong."
        actions={
          <div className="flex items-center gap-2">
            <select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              aria-label="Time range"
              data-testid="activity-range"
              className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
            >
              {RANGES.map((r) => (
                <option key={r.hours} value={String(r.hours)}>
                  {r.label}
                </option>
              ))}
            </select>
            <SkeuoButton type="button" onClick={() => void log.reload()} disabled={log.loading}>
              {log.loading ? "Refreshing…" : "Refresh"}
            </SkeuoButton>
          </div>
        }
      />

      <AdminError error={log.error || summary.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <AdminStat label="Events in range" value={summary.data?.total ?? 0} />
        <AdminStat label="Failures" value={errors} tone={errors ? "warn" : "default"} />
        <AdminStat label="Warnings" value={warnings} tone={warnings ? "warn" : "default"} />
        <AdminStat label="Matching filters" value={total} />
      </div>

      {/* Failures first: an operator opening this page is usually looking for one. */}
      <DevCard title="Recent failures" description="Newest non-ok outcomes in this time range.">
        {summary.loading && !summary.data ? (
          <AdminLoading loading />
        ) : failures.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted" data-testid="activity-no-failures">
            No failures recorded in this range.
          </p>
        ) : (
          <ul className="space-y-2" data-testid="activity-failures">
            {failures.map((f) => (
              <li
                key={f.id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-skeuo-sm border border-surface-border px-3 py-2 text-xs"
              >
                <SkeuoBadge tone={SEVERITY_TONE[f.severity] ?? "muted"}>{f.severity}</SkeuoBadge>
                <span className="font-mono text-text">{f.action}</span>
                <span className="text-text-muted">{f.actor}</span>
                <span className="text-text-muted">
                  {f.resourceType}:{f.resourceId || "—"}
                </span>
                {f.error != null && (
                  <span className="font-mono text-status-danger">
                    {String(f.error).slice(0, 140)}
                  </span>
                )}
                <span className="ml-auto text-text-subtle">{formatWhen(f.createdAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </DevCard>

      <DevCard title="Add a note" description="Record what you concluded while investigating, for whoever looks next.">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <SkeuoInput
            value={note}
            onChange={(e) => {
              setNote(e.target.value);
              setNoteState("idle");
            }}
            placeholder="What did you find, and what did you change?"
            className="flex-1"
            data-testid="activity-note-input"
          />
          <SkeuoButton type="button" onClick={() => void saveNote()} disabled={!note.trim() || noteState === "saving"}>
            {noteState === "saving" ? "Saving…" : "Save note"}
          </SkeuoButton>
        </div>
        {noteState === "saved" && (
          <p className="mt-2 text-xs text-status-success" data-testid="activity-note-saved">
            Note saved to the log.
          </p>
        )}
        {noteError && <p className="mt-2 text-xs text-status-danger">{noteError}</p>}
      </DevCard>

      <DevCard title="All events">
        <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Source"
            data-testid="activity-filter-source"
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
          >
            <option value="">All sources</option>
            {["admin", "subscriber", "webhook", "system"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            aria-label="Outcome"
            data-testid="activity-filter-outcome"
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
          >
            <option value="">Any outcome</option>
            <option value="ok">ok</option>
            <option value="error">error</option>
          </select>
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            aria-label="Severity"
            data-testid="activity-filter-severity"
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
          >
            <option value="">Any severity</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </select>
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            aria-label="Action"
            data-testid="activity-filter-action"
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
          >
            <option value="">All actions</option>
            {actions.map((a) => (
              <option key={a.value} value={a.value}>
                {a.value} ({a.count})
              </option>
            ))}
          </select>
          <select
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            aria-label="Actor"
            data-testid="activity-filter-actor"
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel px-3 py-2 text-sm"
          >
            <option value="">All actors</option>
            {(log.data?.facets?.actors ?? []).map((a) => (
              <option key={a.value} value={a.value}>
                {a.value} ({a.count})
              </option>
            ))}
          </select>
          <SkeuoInput
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="Tenant id"
            aria-label="Tenant id"
            data-testid="activity-filter-tenant"
            className="min-w-[160px] font-mono text-xs"
          />
          <SkeuoInput
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search actor, resource, payload…"
            aria-label="Search activity"
            data-testid="activity-search"
            className="min-w-[180px]"
          />
        </div>

        {/* Row placeholders, not a spinner: the table's shape is known, so an
            empty grid reads as "loading" rather than "empty". */}
        <div
          className="overflow-x-auto"
          aria-busy={log.loading}
          data-testid="activity-table"
          data-loading={log.loading ? "true" : "false"}
        >
          {log.loading && !log.data ? (
            <table className="w-full">
              <tbody data-testid="activity-skeleton">
                {Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b border-surface-border">
                    <td className="py-3 pr-4">
                      <div className="h-3 w-16 animate-pulse rounded bg-surface-panel-raised" />
                    </td>
                    <td className="py-3 pr-4">
                      <div className="h-3 w-40 animate-pulse rounded bg-surface-panel-raised" />
                    </td>
                    <td className="py-3 pr-4">
                      <div className="h-3 w-24 animate-pulse rounded bg-surface-panel-raised" />
                    </td>
                    <td className="py-3 pr-4">
                      <div className="h-3 w-20 animate-pulse rounded bg-surface-panel-raised" />
                    </td>
                    <td className="py-3">
                      <div className="h-3 w-28 animate-pulse rounded bg-surface-panel-raised" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : entries.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-muted" data-testid="activity-empty">
              No events match these filters. Widen the time range or clear a filter.
            </p>
          ) : (
            <SkeuoTable>
              <SkeuoTableHead>
                <SkeuoTableRow>
                  <SkeuoTh>When</SkeuoTh>
                  <SkeuoTh>Action</SkeuoTh>
                  <SkeuoTh>Actor</SkeuoTh>
                  <SkeuoTh>Resource</SkeuoTh>
                  <SkeuoTh>Outcome</SkeuoTh>
                </SkeuoTableRow>
              </SkeuoTableHead>
              <SkeuoTableBody>
                {entries.map((e) => (
                  <SkeuoTableRow
                    key={e.id}
                    data-testid={`activity-row-${e.id}`}
                    onClick={() => setOpenId(openId === e.id ? null : e.id)}
                    className="cursor-pointer"
                  >
                    <SkeuoTd className="whitespace-nowrap text-text-muted">{formatWhen(e.createdAt)}</SkeuoTd>
                    <SkeuoTd className="font-mono">{e.action}</SkeuoTd>
                    <SkeuoTd>
                      <div>{e.actor}</div>
                      <div className="text-[11px] text-text-subtle">{e.source}</div>
                    </SkeuoTd>
                    <SkeuoTd className="font-mono text-xs">
                      {e.resourceType}:{e.resourceId || "—"}
                    </SkeuoTd>
                    <SkeuoTd>
                      <SkeuoBadge tone={SEVERITY_TONE[e.severity] ?? "muted"}>{e.severity}</SkeuoBadge>
                    </SkeuoTd>
                  </SkeuoTableRow>
                ))}
                {openId &&
                  (() => {
                    const entry = entries.find((e) => e.id === openId);
                    if (!entry) return null;
                    return (
                      <SkeuoTableRow data-testid="activity-detail">
                        <SkeuoTd colSpan={5}>
                          <dl className="grid gap-2 text-xs sm:grid-cols-4">
                            <div>
                              <dt className="text-text-subtle">Request id</dt>
                              <dd className="font-mono">{entry.requestId || "—"}</dd>
                            </div>
                            <div>
                              <dt className="text-text-subtle">IP</dt>
                              <dd className="font-mono">{entry.ip || "—"}</dd>
                            </div>
                            <div>
                              <dt className="text-text-subtle">Tenant</dt>
                              <dd className="font-mono">
                                {entry.tenantId ? (
                                  <Link
                                    href={`/dev/admin/tenants/${entry.tenantId}`}
                                    className="underline"
                                  >
                                    {entry.tenantId}
                                  </Link>
                                ) : (
                                  "—"
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-text-subtle">User agent</dt>
                              <dd className="truncate" title={entry.userAgent || undefined}>
                                {entry.userAgent || "—"}
                              </dd>
                            </div>
                          </dl>
                          <pre
                            className="mt-3 max-h-64 overflow-auto rounded-skeuo-sm bg-surface-panel-raised p-3 text-[11px]"
                            data-testid="activity-payload"
                          >
                            {JSON.stringify(entry.payload, null, 2)}
                          </pre>
                        </SkeuoTd>
                      </SkeuoTableRow>
                    );
                  })()}
              </SkeuoTableBody>
            </SkeuoTable>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between text-xs text-text-muted">
          <span data-testid="activity-range-label">
            {total === 0
              ? "No matching events"
              : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
          </span>
          <div className="flex gap-2">
            <SkeuoButton
              type="button"
              size="sm"
              disabled={offset === 0 || log.loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              data-testid="activity-prev"
            >
              Previous
            </SkeuoButton>
            <SkeuoButton
              type="button"
              size="sm"
              disabled={offset + PAGE_SIZE >= total || log.loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              data-testid="activity-next"
            >
              Next
            </SkeuoButton>
          </div>
        </div>
      </DevCard>
    </div>
  );
}