import { cn } from "@/lib/cn";

export function SkeuoTable({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-skeuo-lg border border-surface-border-subtle skeuo-panel", className)}>
      <table className="w-full min-w-[560px] text-left text-sm">{children}</table>
    </div>
  );
}

export function SkeuoTableHead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="border-b border-surface-border-subtle bg-surface-panel-inset text-text-subtle">
      {children}
    </thead>
  );
}

export function SkeuoTableBody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-surface-border-subtle">{children}</tbody>;
}

export function SkeuoTableRow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <tr className={cn("bg-surface-panel transition-colors hover:bg-surface-panel-raised/50", className)}>
      {children}
    </tr>
  );
}

export function SkeuoTh({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th className={cn("px-4 py-3 font-mono text-[10px] uppercase tracking-wider font-medium", className)}>
      {children}
    </th>
  );
}

export function SkeuoTd({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={cn("px-4 py-3", className)}>{children}</td>;
}
