import { Panel } from "@/components/console/Panel";

const FIELDS = [
  ["name", "string", "Caller name"],
  ["budget", "string", "Budget band"],
  ["locality", "string", "Preferred locality"],
  ["next_action", "enum", "Callback / visit / not interested"],
];

export default function DevAgentMemorySchemaPage() {
  return (
    <Panel title="Default compact schema">
      <p className="text-sm text-text-muted">Read-only in MVP. Projection is bounded and server-owned.</p>
      <table className="mt-4 w-full text-left text-sm">
        <thead className="text-text-subtle">
          <tr>
            <th className="py-2 font-medium">Field</th>
            <th className="py-2 font-medium">Type</th>
            <th className="py-2 font-medium">Purpose</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border-subtle">
          {FIELDS.map(([field, type, purpose]) => (
            <tr key={field}>
              <td className="py-2 font-mono text-accent">{field}</td>
              <td className="py-2 text-text-muted">{type}</td>
              <td className="py-2 text-text-muted">{purpose}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
