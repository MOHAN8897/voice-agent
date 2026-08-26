import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "metal";
type Size = "sm" | "md";

export interface SkeuoButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  pressed?: boolean;
}

export const SkeuoButton = forwardRef<HTMLButtonElement, SkeuoButtonProps>(function SkeuoButton(
  { className, variant = "secondary", size = "md", loading, pressed, disabled, children, ...props },
  ref
) {
  const sizes: Record<Size, string> = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
  };

  const variants: Record<Variant, string> = {
    primary: "skeuo-btn-primary text-white",
    secondary: "skeuo-btn-secondary text-text",
    ghost: "text-text-muted hover:text-text hover:bg-surface-panel-raised/60",
    metal: "skeuo-btn-metal text-text",
  };

  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 font-semibold transition-all duration-150",
        "rounded-skeuo-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-chassis",
        "disabled:cursor-not-allowed disabled:opacity-45",
        sizes[size],
        variants[variant],
        pressed && "skeuo-pressed",
        className
      )}
      {...props}
    >
      {loading ? (
        <>
          <span
            className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden
          />
          <span>Please wait…</span>
        </>
      ) : (
        children
      )}
    </button>
  );
});
