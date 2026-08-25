"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";

type Tenant = { id: string; name: string; role: string };

export default function SelectTenantPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    (async () => {
      try {
        const session = await fetch("/api/auth/session").then((r) => r.json());
        const defaultId = session.default_tenant_id || "default";
        setTenants([
          { id: defaultId, name: "Default workspace", role: "Administrator" },
          { id: "staging", name: "Staging (preview)", role: "Developer" },
        ]);
      } catch {
        setTenants([{ id: "default", name: "Default workspace", role: "Administrator" }]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function selectTenant(id: string) {
    document.cookie = `tenant_id=${id}; path=/; max-age=604800; samesite=lax`;
    router.push("/app");
  }

  return (
    <div className="w-full max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight text-text">Select workspace</h1>
      <p className="mt-2 text-sm text-text-muted">Choose the tenant environment for this session.</p>

      {loading ? (
        <p className="mt-8 text-sm text-text-muted" role="status">
          Loading workspaces…
        </p>
      ) : (
        <ul className="mt-8 space-y-3" role="listbox" aria-label="Tenants">
          {tenants.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                role="option"
                onClick={() => selectTenant(t.id)}
                className="w-full rounded-xl border border-surface-border bg-surface-card p-4 text-left transition-colors hover:border-accent/40 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <p className="font-medium text-text">{t.name}</p>
                <p className="mt-1 font-mono text-xs text-text-subtle">{t.id}</p>
                <p className="mt-2 text-xs text-text-muted">{t.role}</p>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button type="button" variant="ghost" className="mt-6 w-full" onClick={() => router.push("/app/login")}>
        Sign in with a different account
      </Button>
    </div>
  );
}
