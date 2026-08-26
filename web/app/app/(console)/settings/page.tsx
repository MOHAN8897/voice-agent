import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { Panel } from "@/components/console/Panel";
import { SkeuoInput } from "@/components/ui/skeuo";

export default function SettingsPage() {
  return (
    <ConsolePage>
      <PageHeader
        eyebrow="Organization"
        title="Settings"
        description="Retention, members, and environment — server RBAC remains authoritative."
      />
      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Panel title="Retention & privacy">
          <label className="block text-sm text-text-muted">
            Call retention (days)
            <SkeuoInput type="number" defaultValue={90} aria-label="Call retention days" className="max-w-xs" />
          </label>
          <p className="mt-2 text-xs text-text-subtle">Default CALL_RETENTION_DAYS=90 from API env.</p>
        </Panel>
        <Panel title="Environments">
          <ul className="space-y-2 text-sm">
            <li className="skeuo-inset rounded-skeuo-sm px-3 py-2 text-text-muted">Development — editable drafts and Test Studio</li>
            <li className="skeuo-inset rounded-skeuo-sm px-3 py-2 text-text-muted">Staging — approved configs, PSTN regression</li>
            <li className="skeuo-env-prod rounded-skeuo-sm border px-3 py-2">Production — immutable active version</li>
          </ul>
        </Panel>
      </div>
    </ConsolePage>
  );
}
