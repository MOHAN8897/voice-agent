"use client";

import { useCallback, useEffect, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";

type Dashboard = { tenants: number; users: number; activeNumbers: number; failedPurchases: number };

async function devFetch(path: string) {
  const res = await fetch(path, { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default function SaasAdminPage() {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [tenants, setTenants] = useState<unknown[]>([]);
  const [assignments, setAssignments] = useState<unknown[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [d, t, a] = await Promise.all([
        devFetch("/api/dev/admin/dashboard"),
        devFetch("/api/dev/admin/tenants"),
        devFetch("/api/dev/admin/phone-assignments"),
      ]);
      setDash(d);
      setTenants((t as { tenants: unknown[] }).tenants || []);
      setAssignments((a as { assignments: unknown[] }).assignments || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-xl font-semibold text-[var(--skeuo-fg)]">SaaS Admin</h1>
      {error && <p className="text-sm text-red-400">Requires dev login + DATABASE_URL. {error}</p>}
      {dash && (
        <div className="grid gap-4 md:grid-cols-4">
          {[
            ["Tenants", dash.tenants],
            ["Users", dash.users],
            ["Numbers", dash.activeNumbers],
            ["Failed purchases", dash.failedPurchases],
          ].map(([label, value]) => (
            <DevCard key={String(label)} title={String(label)}>
              <p className="text-2xl font-mono">{value}</p>
            </DevCard>
          ))}
        </div>
      )}
      <DevCard title="Tenants">
        <pre className="max-h-64 overflow-auto text-xs">{JSON.stringify(tenants, null, 2)}</pre>
      </DevCard>
      <DevCard title="Phone assignments">
        <pre className="max-h-96 overflow-auto text-xs">{JSON.stringify(assignments, null, 2)}</pre>
      </DevCard>
    </div>
  );
}
