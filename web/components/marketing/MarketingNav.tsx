"use client";

import Link from "next/link";
import { BrandMark } from "@/components/brand/BrandMark";

const LINKS = [{ href: "/#how-it-works", label: "How it works" }];

export function MarketingNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-surface-border-subtle/80 bg-surface/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-content items-center justify-between px-6">
        <BrandMark />

        <nav className="hidden items-center gap-8 md:flex" aria-label="Marketing">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-text-muted transition-colors hover:text-text"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <Link href="/#how-it-works" className="btn-primary px-5 py-2 text-sm">
          Learn more
        </Link>
      </div>
    </header>
  );
}
