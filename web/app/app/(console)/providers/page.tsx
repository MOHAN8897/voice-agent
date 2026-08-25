import { apiGet } from "@/lib/api";
import { PageHeader } from "@/components/console/PageHeader";
import { StatusBadge } from "@/components/console/StatusBadge";
import { EmptyState } from "@/components/console/EmptyState";

type ProviderRow = {
  id: string;
  label?: string;
  capabilities?: string[];
  status?: string;
};

export default async function ProvidersPage() {
  let providers: ProviderRow[] = [];
  let configMode = "—";
  try {
    const data = await apiGet<{ providers?: ProviderRow[]; config_mode?: string }>("/api/providers/catalog");
    providers = data.providers || [];
    configMode = data.config_mode || "—";
  } catch {
    providers = [];
  }

  return (
    <div>
      <PageHeader
        eyebrow="Catalog"
        title="Providers"
        description={`Read-only provider catalog and language gates. Resolution mode: ${configMode}.`}
      />

      {providers.length === 0 ? (
        <div className="mt-8">
          <EmptyState title="Catalog unavailable" body="Start the API to load STT, LLM, and TTS providers." />
        </div>
      ) : (
        <div className="mt-8 overflow-x-auto rounded-2xl border border-surface-border-subtle">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-surface-elevated text-text-subtle">
              <tr>
                <th className="px-4 py-3 font-medium">Provider</th>
                <th className="px-4 py-3 font-medium">Capabilities</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border-subtle bg-surface-card">
              {providers.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3 font-medium text-text">{p.label || p.id}</td>
                  <td className="px-4 py-3 text-text-muted">{(p.capabilities || []).join(", ") || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge tone={p.status === "enabled" ? "success" : "muted"}>{p.status || "listed"}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
