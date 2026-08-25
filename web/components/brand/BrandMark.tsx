import Link from "next/link";

type BrandMarkProps = {
  href?: string;
  compact?: boolean;
  className?: string;
};

export function BrandMark({ href = "/", compact = false, className = "" }: BrandMarkProps) {
  const inner = (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-dim font-mono text-sm font-semibold text-accent"
        aria-hidden
      >
        V
      </span>
      {!compact && <span className="text-xl font-semibold tracking-tight text-text">Vāṇi</span>}
    </span>
  );

  if (!href) return inner;
  return (
    <Link href={href} className="group">
      {inner}
    </Link>
  );
}
