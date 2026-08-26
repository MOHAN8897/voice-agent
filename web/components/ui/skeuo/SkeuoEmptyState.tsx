import Link from "next/link";
import { SkeuoButton } from "./SkeuoButton";

export function SkeuoEmptyState({
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
  return (
    <div className="skeuo-inset rounded-skeuo-lg border border-dashed border-surface-border-subtle px-6 py-14 text-center">
      <div className="mx-auto mb-4 h-10 w-10 rounded-skeuo-md border border-surface-border-subtle skeuo-panel flex items-center justify-center">
        <span className="font-mono text-xs text-text-subtle">—</span>
      </div>
      <p className="font-medium text-text">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-text-muted">{body}</p>
      {actionHref && actionLabel && (
        <Link href={actionHref} className="mt-6 inline-block">
          <SkeuoButton variant="primary">{actionLabel}</SkeuoButton>
        </Link>
      )}
    </div>
  );
}
