import { apiGet } from "@/lib/api";
import Link from "next/link";
import { PageHeader } from "@/components/console/PageHeader";
import { EmptyState } from "@/components/console/EmptyState";
import { StatusBadge, dispositionTone } from "@/components/console/StatusBadge";

export default async function CallsPage() {
  let calls: Array<{
    call_id: string;
    disposition?: string;
    channel?: string;
    started_at?: string;
    duration_s?: number;
  }> = [];
  try {
    const data = await apiGet<{
      calls?: Array<{ call_id: string; disposition?: string; channel?: string; started_at?: string; duration_s?: number }>;
    }>("/api/calls");
    calls = data.calls || [];
  } catch {
    calls = [];
  }

  return (
    <div>
      <PageHeader
        eyebrow="Review"
        title="Calls"
        description="Transcript, memory, audio, and disposition — one row per finalized call."
      />

      {calls.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No calls yet"
            body="Start a voice session in Test Studio to create your first call archive."
            actionHref="/app/test-studio"
            actionLabel="Open Test Studio"
          />
        </div>
      ) : (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-surface-border-subtle">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-surface-elevated text-text-subtle">
              <tr>
                <th className="px-4 py-3 font-medium">Call</th>
                <th className="px-4 py-3 font-medium">Channel</th>
                <th className="px-4 py-3 font-medium">Disposition</th>
                <th className="px-4 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border-subtle bg-surface-card">
              {calls.map((c) => (
                <tr key={c.call_id} className="hover:bg-surface-raised/60">
                  <td className="px-4 py-3">
                    <Link href={`/app/calls/${c.call_id}`} className="font-mono text-accent hover:underline">
                      {c.call_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-text-muted">{c.channel || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge tone={dispositionTone(c.disposition)}>{c.disposition || "pending"}</StatusBadge>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-text-subtle">{c.started_at || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
