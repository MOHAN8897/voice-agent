import { PromotionPanel } from "@/components/dev/PromotionPanel";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevPromotionPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Release"
        title="Promotion"
        description="Move validated tier assignments across environments with audit-ready reasons."
      />
      <PromotionPanel />
    </div>
  );
}
