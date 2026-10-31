import React from 'react';
import { Calculator } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { PageHeader } from '../ui/PageHeader';
import { UsageCalculator } from '../../components/UsageCalculator';
import { usePricingCatalog } from '../../lib/usePricingCatalog';

export function UsageCalculatorModule() {
  const pricing = usePricingCatalog();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage calculator"
        description="Estimate a month of phone calls by number of calls or by talk time. Your wallet and invoices show what was actually charged."
      />

      <SolidCard padding="p-5 sm:p-6" className="min-w-0">
        <h2 className="flex items-center gap-2 text-title text-ink mb-4">
          <Calculator size={16} className="text-fg-subtle" aria-hidden="true" />
          Estimate by voice tier
        </h2>
        <UsageCalculator
          catalog={pricing.data}
          loading={pricing.loading}
          error={pricing.error}
          onRetry={pricing.reload}
        />
      </SolidCard>

      <p className="text-meta text-fg-muted">
        Estimates use the published per-minute phone rate, with GST shown when it applies.
        Each call keeps the rate it started with, and your wallet records the exact amount charged.
      </p>
    </div>
  );
}
