import { PageHeader } from "@/components/console/PageHeader";
import { GlobalCallsWorkbench } from "@/components/admin/GlobalCallsWorkbench";

export default function DevAdminCallsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Platform operations & auditing"
        title="Global calls & supplier cost explorer"
        description="Inspect all live and completed calls across all tenants, verify carrier CDR billing, and audit exact wholesale supplier costs and margins."
      />

      <GlobalCallsWorkbench />
    </div>
  );
}
