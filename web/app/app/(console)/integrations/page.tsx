import { apiGet } from "@/lib/api";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { Panel } from "@/components/console/Panel";
import { StatusBadge } from "@/components/console/StatusBadge";

export default async function IntegrationsPage() {
  let plivo: Record<string, unknown> = {};
  let numbers: Array<{ e164: string; status: string }> = [];
  try {
    plivo = await apiGet("/api/plivo/status");
    const pn = await apiGet<{ numbers?: Array<{ e164: string; status: string }> }>("/api/phone-numbers");
    numbers = pn.numbers || [];
  } catch {
    /* stub */
  }

  return (
    <ConsolePage>
      <PageHeader
        eyebrow="Connect"
        title="Integrations"
        description="Plivo telephony, numbers, and future CRM/webhook connectors."
      />
      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Panel title="Plivo telephony">
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between items-center skeuo-inset rounded-skeuo-sm px-3 py-2">
              <dt className="text-text-muted">Enabled</dt>
              <dd>
                <StatusBadge tone={plivo.enabled ? "success" : "muted"}>{String(plivo.enabled ?? false)}</StatusBadge>
              </dd>
            </div>
            <div className="flex justify-between items-center skeuo-inset rounded-skeuo-sm px-3 py-2">
              <dt className="text-text-muted">Configured</dt>
              <dd>
                <StatusBadge tone={plivo.configured ? "success" : "warning"}>{String(plivo.configured ?? false)}</StatusBadge>
              </dd>
            </div>
          </dl>
        </Panel>
        <Panel title="Phone numbers">
          {numbers.length === 0 ? (
            <p className="text-sm text-text-muted">No numbers provisioned.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {numbers.map((n) => (
                <li key={n.e164} className="flex justify-between items-center skeuo-inset rounded-skeuo-sm px-3 py-2 font-mono">
                  <span>{n.e164}</span>
                  <StatusBadge>{n.status}</StatusBadge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </ConsolePage>
  );
}
