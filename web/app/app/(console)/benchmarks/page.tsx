import { PageHeader } from "@/components/console/PageHeader";
import { Panel } from "@/components/console/Panel";

export default function BenchmarksPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Evaluation"
        title="Benchmarks"
        description="Combination comparison is gated until ENABLE_BENCHMARKS=true."
      />
      <div className="mt-8">
        <Panel>
          <p className="font-medium text-warning">Not configured</p>
          <p className="mt-2 text-sm text-text-muted">
            Benchmark auto-runs are not enabled yet. Scenarios, combination selection, and promotion stay inert until
            ENABLE_BENCHMARKS is turned on in your environment.
          </p>
        </Panel>
      </div>
    </div>
  );
}
