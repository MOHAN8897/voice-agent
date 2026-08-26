import { cn } from "@/lib/cn";

export function ConsolePage({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("console-page-enter", className)}>{children}</div>;
}
