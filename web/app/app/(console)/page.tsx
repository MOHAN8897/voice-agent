import { apiGet } from "@/lib/api";
import { ConsolePage } from "@/components/console/ConsolePage";
import { OverviewInstrumentation } from "@/components/console/OverviewInstrumentation";

export default async function OverviewPage() {
  let health: Record<string, unknown> = {};
  let metrics: Record<string, unknown> = {};
  try {
    health = await apiGet("/api/health");
  } catch {
    health = { ok: false };
  }
  try {
    metrics = await apiGet("/api/metrics");
  } catch {
    metrics = {};
  }

  return (
    <ConsolePage>
      <OverviewInstrumentation health={health} metrics={metrics} />
    </ConsolePage>
  );
}