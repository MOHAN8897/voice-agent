import React from 'react';
import { Calculator } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { UsageCalculator } from '../../components/UsageCalculator';
import { usePricingCatalog } from '../../lib/usePricingCatalog';

export function UsageCalculatorModule() {
  const pricing = usePricingCatalog();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
          Usage calculator
        </h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Estimate a month of phone calls against the published per-minute rate, by calls or by talk
          time. The wallet and invoices stay the source of truth for what was actually charged.
        </p>
      </div>

      <SolidCard padding="p-5 sm:p-6">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#0F0E17] mb-4">
          <Calculator size={15} className="text-[#6344E7]" aria-hidden="true" />
          Estimate by voice tier
        </div>
        <UsageCalculator
          catalog={pricing.data}
          loading={pricing.loading}
          error={pricing.error}
          onRetry={pricing.reload}
        />
      </SolidCard>

      <p className="text-[11px] text-[#8C879A]">
        Estimates apply the published per-minute phone rate; GST is shown when tax is configured.
        Each call locks its rate when it starts, and the wallet records the exact amount charged.
      </p>
    </div>
  );
}
