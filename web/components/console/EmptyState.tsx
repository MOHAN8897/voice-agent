import { SkeuoEmptyState } from "@/components/ui/skeuo/SkeuoEmptyState";

export function EmptyState({
  title,
  body,
  actionHref,
  actionLabel,
}: {
  title: string;
  body: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return <SkeuoEmptyState title={title} body={body} actionHref={actionHref} actionLabel={actionLabel} />;
}
