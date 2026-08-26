import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

export function Panel({
  title,
  children,
  className = "",
  description,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  description?: string;
}) {
  return (
    <SkeuoPanel title={title} description={description} className={className} padding="md">
      {children}
    </SkeuoPanel>
  );
}
