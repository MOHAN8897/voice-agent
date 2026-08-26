"use client";

import { useState } from "react";
import { BrandMark } from "@/components/brand/BrandMark";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { SkeuoButton } from "@/components/ui/skeuo";
import { cn } from "@/lib/cn";

export function InstrumentSidebar({
  subtitle,
  nav,
  footer,
  className,
}: {
  subtitle: string;
  nav: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "hidden w-[15.5rem] shrink-0 flex-col border-r border-surface-border-subtle skeuo-panel md:flex",
        className
      )}
    >
      <div className="border-b border-surface-border-subtle px-4 py-4">
        <BrandMark />
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-text-subtle">{subtitle}</p>
      </div>
      <nav className="flex-1 overflow-y-auto p-3" aria-label="Primary">{nav}</nav>
      {footer && <div className="border-t border-surface-border-subtle p-3 text-xs space-y-1">{footer}</div>}
    </aside>
  );
}

export function MobileShellHeader({
  open,
  onToggle,
  nav,
  footer,
}: {
  open: boolean;
  onToggle: () => void;
  nav: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <>
      <header className="flex items-center justify-between border-b border-surface-border-subtle bg-surface-panel px-4 py-3 md:hidden">
        <BrandMark compact />
        <SkeuoButton type="button" variant="secondary" size="sm" onClick={onToggle} aria-expanded={open}>
          Menu
        </SkeuoButton>
      </header>
      {open && (
        <nav className="border-b border-surface-border-subtle bg-surface-panel p-3 md:hidden" aria-label="Mobile">
          {nav}
          {footer && <div className="mt-3 border-t border-surface-border-subtle pt-3">{footer}</div>}
        </nav>
      )}
    </>
  );
}
