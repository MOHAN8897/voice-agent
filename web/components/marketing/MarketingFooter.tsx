import { BrandMark } from "@/components/brand/BrandMark";

export function MarketingFooter() {
  return (
    <footer className="border-t border-surface-border-subtle bg-surface-elevated">
      <div className="mx-auto max-w-content px-6 py-16">
        <div className="max-w-md">
          <BrandMark />
          <p className="mt-4 text-sm leading-relaxed text-text-muted">
            Production voice control plane for businesses serving Telugu-speaking customers across India.
          </p>
        </div>
        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-surface-border-subtle pt-8 text-sm text-text-subtle md:flex-row">
          <p>© {new Date().getFullYear()} Vāṇi Voice Platform</p>
          <p className="font-mono text-xs">Memory · Disposition · Call archive</p>
        </div>
      </div>
    </footer>
  );
}
