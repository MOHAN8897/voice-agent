import { cn } from "@/lib/cn";

export function SkeuoInput({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm text-text",
        "shadow-inset placeholder:text-text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
        className
      )}
      {...props}
    />
  );
}
