import { Suspense } from "react";
import { TeamWorkspace } from "@/components/admin/team/TeamWorkspace";

/**
 * Roles & access: platform-admin management, role catalogue and admin-team audit.
 * Served from `/api/dev/admin/team*`, which reads the same RBAC matrix the API
 * authorizes against, so this screen cannot disagree with enforcement.
 */
export default function AdminAccessPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-text-muted">Loading roles & access…</p>}>
      <TeamWorkspace />
    </Suspense>
  );
}
