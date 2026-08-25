import { PageHeader } from "@/components/console/PageHeader";
import { Panel } from "@/components/console/Panel";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Organization"
        title="Settings"
        description="Retention, members, and environment — server RBAC remains authoritative."
      />
      <div className="mt-8 grid gap-4 lg:grid-cols-2">
        <Panel title="Retention & privacy">
          <label className="block text-sm text-text-muted">
            Call retention (days)
            <input
              type="number"
              defaultValue={90}
              className="mt-2 w-full max-w-xs rounded-xl border border-surface-border bg-surface px-3 py-2 text-text"
              aria-label="Call retention days"
            />
          </label>
          <p className="mt-2 text-xs text-text-subtle">Default CALL_RETENTION_DAYS=90 from API env.</p>
        </Panel>
        <Panel title="Environments">
          <ul className="space-y-2 text-sm text-text-muted">
            <li>Development — editable drafts and Test Studio</li>
            <li>Staging — approved configs, PSTN regression</li>
            <li>Production — immutable active version</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
