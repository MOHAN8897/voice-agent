"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { BrandMark } from "@/components/brand/BrandMark";

const LINKS = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/docs", label: "Docs" },
  { href: "/pricing", label: "Pricing" },
];

export function MarketingNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-surface-border-subtle/80 bg-surface/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-content items-center justify-between px-6">
        <BrandMark />

        <nav className="hidden items-center gap-8 md:flex" aria-label="Marketing">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-sm font-medium transition-colors ${
                pathname === link.href ? "text-text" : "text-text-muted hover:text-text"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:block">
          <Link href="/app" className="btn-primary px-5 py-2 text-sm">
            Open Console
          </Link>
        </div>

        <button
          type="button"
          className="rounded-lg border border-surface-border p-2 md:hidden"
          aria-label="Toggle menu"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <nav className="border-t border-surface-border-subtle px-6 py-4 md:hidden" aria-label="Mobile">
          <div className="flex flex-col gap-3">
            {LINKS.map((link) => (
              <Link key={link.href} href={link.href} className="text-sm text-text-muted" onClick={() => setOpen(false)}>
                {link.label}
              </Link>
            ))}
            <Link href="/app" className="btn-primary text-center" onClick={() => setOpen(false)}>
              Open Console
            </Link>
          </div>
        </nav>
      )}
    </header>
  );
}
