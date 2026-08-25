import { PageHeader } from "@/components/console/PageHeader";
import { Panel } from "@/components/console/Panel";

export default function DevBenchmarksPage() {
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
            Benchmark auto-runs are disabled by default. Set ENABLE_BENCHMARKS=true in Environment when scenarios are
            ready. Dev portal mirrors the business console shell until then.
          </p>
        </Panel>
      </div>
    </div>
  );
}
