import { SkeuoMeter } from "@/components/ui/skeuo/SkeuoMeter";

export function StatCard({
  label,
  value,
  hint,
  unit,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  unit?: string;
  tone?: "default" | "ok" | "warn" | "accent";
}) {
  return <SkeuoMeter label={label} value={value} hint={hint} unit={unit} tone={tone} />;
}
