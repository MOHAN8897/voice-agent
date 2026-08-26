import { cn } from "@/lib/cn";

export function SkeuoTextarea({
  className,
  error,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { error?: boolean }) {
  return (
    <textarea
      className={cn(
        "w-full rounded-skeuo-sm border bg-surface-panel-inset px-3 py-2 font-mono text-sm leading-relaxed text-text",
        "shadow-inset placeholder:text-text-subtle",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/35",
        error ? "border-status-error/50" : "border-surface-border-subtle",
        className
      )}
      {...props}
    />
  );
}
