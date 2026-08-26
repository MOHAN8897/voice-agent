import { SkeuoBadge, dispositionTone } from "@/components/ui/skeuo/SkeuoBadge";

export function StatusBadge({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "success" | "warning" | "info" | "muted" | "accent" | "live" | "error";
}) {
  const map: Record<string, "success" | "warning" | "info" | "muted" | "accent" | "live" | "error"> = {
    success: "success",
    warning: "warning",
    warn: "warning",
    info: "info",
    muted: "muted",
    accent: "accent",
    live: "live",
    error: "error",
  };
  return <SkeuoBadge tone={map[tone] || "muted"}>{children}</SkeuoBadge>;
}

export { dispositionTone };
