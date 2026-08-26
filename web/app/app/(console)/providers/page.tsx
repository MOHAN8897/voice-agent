import { apiGet } from "@/lib/api";
import { ConsolePage } from "@/components/console/ConsolePage";
import { EmptyState } from "@/components/console/EmptyState";
import { PageHeader } from "@/components/console/PageHeader";
import { StatusBadge } from "@/components/console/StatusBadge";
import { SkeuoTable, SkeuoTableBody, SkeuoTableHead, SkeuoTableRow, SkeuoTd, SkeuoTh } from "@/components/ui/skeuo";

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
    <ConsolePage>
      <PageHeader
        eyebrow="Hardware rack"
        title="Providers"
        description={`STT, LLM, and TTS modules. Resolution mode: ${configMode}.`}
      />

      {providers.length === 0 ? (
        <div className="mt-8">
          <EmptyState title="Catalog unavailable" body="Start the API to load STT, LLM, and TTS providers." />
        </div>
      ) : (
        <SkeuoTable className="mt-8">
          <SkeuoTableHead>
            <tr>
              <SkeuoTh>Provider</SkeuoTh>
              <SkeuoTh>Capabilities</SkeuoTh>
              <SkeuoTh>Status</SkeuoTh>
            </tr>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {providers.map((p) => (
              <SkeuoTableRow key={p.id}>
                <SkeuoTd className="font-medium text-text">{p.label || p.id}</SkeuoTd>
                <SkeuoTd className="text-text-muted">{(p.capabilities || []).join(", ") || "—"}</SkeuoTd>
                <SkeuoTd>
                  <StatusBadge tone={p.status === "enabled" ? "success" : "muted"}>{p.status || "listed"}</StatusBadge>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
          </SkeuoTableBody>
        </SkeuoTable>
      )}
    </ConsolePage>
  );
}
