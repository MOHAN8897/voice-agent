"use client";

import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";
import {
  ENTITY_FIELD_LABELS,
  hasScriptEntityValues,
  type ScriptEntities,
} from "@/lib/script-entities";

const inputCls =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50";

type Props = {
  entities: ScriptEntities;
  scriptHasTags?: boolean;
  disabled?: boolean;
  onChange: (next: ScriptEntities) => void;
  onApplyToScript?: () => void;
  className?: string;
};

export function ScriptEntityTagsPanel({
  entities,
  scriptHasTags,
  disabled,
  onChange,
  onApplyToScript,
  className,
}: Props) {
  const hasAny = hasScriptEntityValues(entities);
  const keys = Object.keys(ENTITY_FIELD_LABELS) as (keyof ScriptEntities)[];

  const jsonPreview = JSON.stringify({ script_entities: entities }, null, 2);

  return (
    <div className={cn("rounded-skeuo-sm border border-surface-border-subtle p-4", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-text">Dynamic entity tags</p>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Structured @tags in the compiled script — used for PSTN prewarm opening and Gemini brain pins. Edit values,
            then apply to update the calling script header.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <SkeuoBadge tone={hasAny ? "success" : "muted"} className="text-[10px]">
              {hasAny ? "Tags populated" : "No tags yet"}
            </SkeuoBadge>
            {scriptHasTags ? (
              <SkeuoBadge tone="muted" className="text-[10px]">Stored with script</SkeuoBadge>
            ) : null}
          </div>
        </div>
        {onApplyToScript ? (
          <SkeuoButton
            type="button"
            variant="secondary"
            size="sm"
            disabled={disabled || !hasAny}
            onClick={onApplyToScript}
          >
            Apply tags to script
          </SkeuoButton>
        ) : null}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {keys.map((key) => (
          <label key={key} className="block text-xs">
            <span className="text-text-muted">{ENTITY_FIELD_LABELS[key]}</span>
            {key === "opening_line" ? (
              <textarea
                disabled={disabled}
                className={cn(inputCls, "mt-1 min-h-[72px] resize-y font-mono text-[11px]")}
                value={entities[key]}
                onChange={(e) => onChange({ ...entities, [key]: e.target.value })}
              />
            ) : (
              <input
                disabled={disabled}
                className={cn(inputCls, "mt-1 font-mono text-[11px]")}
                value={entities[key]}
                onChange={(e) => onChange({ ...entities, [key]: e.target.value })}
              />
            )}
          </label>
        ))}
      </div>
      {hasAny ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-[11px] font-medium text-text-muted">JSON (script_entities)</summary>
          <pre className="mt-2 rounded-lg border border-surface-border-subtle bg-surface-raised/40 p-2 font-mono text-[10px] text-text-muted whitespace-pre-wrap">
            {jsonPreview}
          </pre>
        </details>
      ) : (
        <p className="mt-3 text-[11px] text-text-subtle">
          Create agent script to generate @entity tags, or apply after editing the brief.
        </p>
      )}
    </div>
  );
}
