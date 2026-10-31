import { Suspense } from "react";
import { NumberPurchasesWorkspace } from "@/components/admin/purchases/NumberPurchasesWorkspace";

export default function AdminNumberPurchasesRoute() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-text-muted">Loading number purchases…</p>}>
      <NumberPurchasesWorkspace />
    </Suspense>
  );
}
