import Link from "next/link";
import { BrandMark } from "@/components/brand/BrandMark";

const FOOTER_LINKS = {
  Product: [
    { href: "/app", label: "Console" },
    { href: "/app/agents", label: "Agents" },
    { href: "/app/calls", label: "Calls" },
    { href: "/pricing", label: "Pricing" },
  ],
  Resources: [
    { href: "/docs", label: "Documentation" },
    { href: "/app/login", label: "Sign in" },
  ],
};

export function MarketingFooter() {
  return (
    <footer className="border-t border-surface-border-subtle bg-surface-elevated">
      <div className="mx-auto max-w-content px-6 py-16">
        <div className="grid gap-12 md:grid-cols-3">
          <div>
            <BrandMark />
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-text-muted">
              Production voice control plane for businesses serving Telugu-speaking customers across India.
            </p>
          </div>
          {Object.entries(FOOTER_LINKS).map(([title, links]) => (
            <div key={title}>
              <p className="label-caps text-text-subtle">{title}</p>
              <ul className="mt-4 space-y-2.5">
                {links.map((link) => (
                  <li key={link.label}>
                    <Link href={link.href} className="text-sm text-text-muted transition-colors hover:text-text">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-surface-border-subtle pt-8 text-sm text-text-subtle md:flex-row">
          <p>© {new Date().getFullYear()} Vāṇi Voice Platform</p>
          <p className="font-mono text-xs">Memory · Disposition · Call archive</p>
        </div>
      </div>
    </footer>
  );
}
