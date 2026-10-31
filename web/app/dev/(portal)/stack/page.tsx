import { PstnVoiceProfileWorkbench } from "@/components/dev/PstnVoiceProfileWorkbench";
import { PricingMerchandisingEditor } from "@/components/dev/PricingMerchandisingEditor";
import { GstBillingSettings } from "@/components/dev/GstBillingSettings";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevStackPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform voice configuration"
        title="Voice stacks & PSTN tiers"
        description="Configure each tier's speech stack, voice knobs and price, verify it, and choose which tiers tenants can use. Changes are saved explicitly per tier."
      />
      <div className="mt-6">
        <PstnVoiceProfileWorkbench />
      </div>
      <section className="mt-10 space-y-4" aria-labelledby="pricing-tags-heading">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-subtle">
            Public pricing
          </p>
          <h2 id="pricing-tags-heading" className="mt-1 text-xl font-semibold text-text">
            Marketing tags &amp; featured tier
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Badges and the highlighted tier on the public pricing cards and usage calculator.
            Shelf prices are the tier card prices configured above (read-only here).
          </p>
        </div>
        <PricingMerchandisingEditor />
      </section>
      <section className="mt-10 space-y-4" aria-labelledby="gst-billing-heading">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-subtle">
            Billing &amp; compliance
          </p>
          <h2 id="gst-billing-heading" className="mt-1 text-xl font-semibold text-text">
            GST charges &amp; invoice identity
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Tax rate, supplier identity, place-of-supply rules and invoice numbering used for every
            tenant recharge. Kept beside the retail prices so the shelf price and the tax applied to
            it are configured in one place.
          </p>
        </div>
        <GstBillingSettings />
      </section>
    </div>
  );
}
