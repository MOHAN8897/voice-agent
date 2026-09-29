"use client";

import { DevCard } from "@/components/dev/DevCard";
import { AdminError, AdminLoading, AdminPageHeader } from "@/components/admin/AdminNav";
import { SkeuoBadge } from "@/components/ui/skeuo";
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

  const roles = data?.roles ?? [];
  const permissions = data?.permissions ?? [];

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
                  {permissions.map((p) => (
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
                </tbody>
              </table>
            </div>
          </DevCard>
        </>
      )}
    </div>
  );
}
