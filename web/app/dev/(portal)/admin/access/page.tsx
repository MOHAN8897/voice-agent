"use client";

import { useMemo, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { AdminError, AdminLoading, AdminPageHeader } from "@/components/admin/AdminNav";
import { SkeuoBadge, SkeuoInput } from "@/components/ui/skeuo";
import { useAdminResource } from "@/lib/useAdminResource";

type Access = {
  roles: string[];
  permissions: Array<{ name: string; roles: string[]; devOnly: boolean }>;
  currentRole: string;
  currentSubject: string;
  currentPermissions: string[];
};

/**
 * The matrix is rendered from `/api/dev/admin/access`, which reads
 * `server/auth/rbac.py` directly. It is deliberately read-only here: a UI copy of
 * the permission table would drift from what the API actually enforces.
 */
export default function AdminAccessPage() {
  const { data, error, loading } = useAdminResource<Access>("/api/dev/admin/access");

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [scopeFilter, setScopeFilter] = useState("all");

  const roles = data?.roles ?? [];
  const permissions = data?.permissions ?? [];

  const filteredPermissions = useMemo(() => {
    return permissions.filter((p) => {
      if (roleFilter !== "all" && !p.roles.includes(roleFilter)) return false;
      if (scopeFilter === "dev_only" && !p.devOnly) return false;
      if (scopeFilter === "standard" && p.devOnly) return false;
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return p.name.toLowerCase().includes(q);
    });
  }, [permissions, roleFilter, scopeFilter, search]);

  const hasFilters = Boolean(search.trim() || roleFilter !== "all" || scopeFilter !== "all");

  function resetFilters() {
    setSearch("");
    setRoleFilter("all");
    setScopeFilter("all");
  }

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Roles & access"
        description="Who can do what. Served by the server from the same table it authorizes against, so this screen cannot disagree with enforcement."
      />

      <AdminError error={error} />
      <AdminLoading loading={loading} />

      {data && (
        <>
          <DevCard title="Your session">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <SkeuoBadge tone="info">{data.currentRole}</SkeuoBadge>
              <span className="text-text-muted">as {data.currentSubject}</span>
              <span className="text-text-muted">
                · {data.currentPermissions.length} of {permissions.length} permissions
              </span>
            </div>
          </DevCard>

          <DevCard
            title="Permission matrix"
            description="Rows are enforced server-side. A missing tick is a 403, not a hidden button."
          >
            {/* Search and Filters */}
            <div className="mb-4 space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-text-muted">Search permission</label>
                  <SkeuoInput
                    placeholder="Filter by name (e.g. dev.admin, voice)…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Filter permissions"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-text-muted">Granted to role</label>
                  <select
                    value={roleFilter}
                    onChange={(e) => setRoleFilter(e.target.value)}
                    className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
                  >
                    <option value="all">All roles</option>
                    {roles.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-text-muted">Scope</label>
                  <select
                    value={scopeFilter}
                    onChange={(e) => setScopeFilter(e.target.value)}
                    className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
                  >
                    <option value="all">All scopes</option>
                    <option value="dev_only">Dev Platform Only</option>
                    <option value="standard">Tenant Facing</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-surface-border-subtle pt-2 text-xs text-text-muted">
                <span>
                  Showing <strong className="text-text">{filteredPermissions.length}</strong> of{" "}
                  <strong className="text-text">{permissions.length}</strong> permissions
                </span>
                {hasFilters && (
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="text-accent-primary hover:underline"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="sticky left-0 bg-surface-panel px-3 py-2 text-left text-xs uppercase tracking-wider text-text-subtle">
                      Permission
                    </th>
                    {roles.map((r) => (
                      <th
                        key={r}
                        className="px-2 py-2 text-center text-[10px] font-semibold uppercase tracking-wider text-text-subtle"
                      >
                        {r.replace(/_/g, "\n")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredPermissions.map((p) => (
                    <tr key={p.name} className="border-t border-surface-border-subtle">
                      <td className="sticky left-0 bg-surface-panel px-3 py-2">
                        <span className="font-mono text-xs text-text">{p.name}</span>
                        {p.devOnly && (
                          <SkeuoBadge tone="warning" className="ml-2">
                            dev
                          </SkeuoBadge>
                        )}
                      </td>
                      {roles.map((r) => {
                        const has = p.roles.includes(r);
                        const mine = r === data.currentRole;
                        return (
                          <td key={r} className="px-2 py-2 text-center">
                            <span
                              aria-label={`${p.name} for ${r}: ${has ? "allowed" : "denied"}`}
                              className={`inline-block h-2.5 w-2.5 rounded-full ${
                                has
                                  ? mine
                                    ? "bg-accent-primary"
                                    : "bg-status-success/70"
                                  : "bg-surface-border-subtle"
                              }`}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {filteredPermissions.length === 0 && (
                    <tr>
                      <td colSpan={roles.length + 1} className="py-6 text-center text-sm text-text-muted">
                        No permissions match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </DevCard>
        </>
      )}
    </div>
  );
}
