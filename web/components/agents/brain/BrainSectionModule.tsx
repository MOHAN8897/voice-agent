"use client";

import { useState } from "react";
import { BRAIN_SECTION_LABELS } from "@/lib/constants";
import type { BrainSection, ValidationIssue } from "@/lib/brain-utils";
import { charLimitFor, issuesForSection, sectionCompletion } from "@/lib/brain-utils";
import { cn } from "@/lib/cn";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoStatusLight } from "@/components/ui/skeuo/SkeuoStatusLight";
import { SkeuoTextarea } from "@/components/ui/skeuo/SkeuoTextarea";

function labelFor(section: BrainSection): string {
  return BRAIN_SECTION_LABELS[section.type] || section.title;
}

export function BrainSectionModule({
  section,
  issues,
  onChange,
  defaultOpen = false,
}: {
  section: BrainSection;
  issues: ValidationIssue[];
  onChange: (raw_text: string) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [preview, setPreview] = useState(false);
  const completion = sectionCompletion(section);
  const sectionIssues = issuesForSection(issues, section.section_id);
  const blocking = sectionIssues.some((i) => i.severity === "blocking");
  const warning = sectionIssues.some((i) => i.severity === "warning");
  const maxChars = charLimitFor(section);
  const charCount = (section.raw_text || "").length;

  const statusLed = blocking ? "error" : warning ? "warn" : completion >= 80 ? "ok" : completion > 0 ? "info" : "idle";

  return (
    <article className="rounded-skeuo-md border border-surface-border-subtle skeuo-panel overflow-hidden transition-all duration-200">
      <header className="flex flex-wrap items-center gap-3 border-b border-surface-border-subtle px-4 py-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <SkeuoStatusLight status={statusLed} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-text">{labelFor(section)}</p>
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{section.type}</p>
          </div>
        </button>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="skeuo-inset rounded-skeuo-sm px-2 py-1">
            <span className="font-mono text-[10px] text-text-muted">{completion}%</span>
            <div className="mt-1 h-1 w-16 overflow-hidden rounded-full bg-surface-panel-raised">
              <div
                className="h-full bg-accent-primary/70 transition-all duration-300"
                style={{ width: `${completion}%` }}
              />
            </div>
          </div>
          <SkeuoBadge tone={section.enabled ? "success" : "muted"}>
            {section.enabled ? "Enabled" : "Off"}
          </SkeuoBadge>
          <SkeuoButton type="button" variant="ghost" size="sm" onClick={() => setPreview((v) => !v)}>
            {preview ? "Edit" : "Preview"}
          </SkeuoButton>
          <SkeuoButton type="button" variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
            {open ? "Collapse" : "Expand"}
          </SkeuoButton>
        </div>
      </header>

      {open && (
        <div className="p-4 space-y-3 brain-section-enter">
          {sectionIssues.length > 0 && (
            <ul className="space-y-1.5">
              {sectionIssues.map((issue) => (
                <li
                  key={`${issue.code}-${issue.message}`}
                  className={cn(
                    "rounded-skeuo-sm px-3 py-2 text-xs",
                    issue.severity === "blocking"
                      ? "border border-status-error/30 bg-status-error/10 text-status-error"
                      : "border border-status-warning/30 bg-status-warning/10 text-status-warning"
                  )}
                >
                  {issue.message}
                </li>
              ))}
            </ul>
          )}

          {preview ? (
            <div className="skeuo-brain-optimized rounded-skeuo-md p-4">
              <p className="label-caps text-text-subtle">Section preview</p>
              <pre className="mt-2 whitespace-pre-wrap font-mono text-sm leading-relaxed text-text-secondary">
                {section.raw_text || "— empty —"}
              </pre>
            </div>
          ) : (
            <div className="skeuo-brain-raw rounded-skeuo-md p-3">
              <p className="mb-2 label-caps text-text-subtle">User source</p>
              <SkeuoTextarea
                rows={8}
                value={section.raw_text}
                onChange={(e) => onChange(e.target.value)}
                aria-label={labelFor(section)}
                error={blocking}
                maxLength={maxChars}
              />
              <p className="mt-2 font-mono text-[10px] text-text-subtle">
                {charCount.toLocaleString()} / {maxChars.toLocaleString()} chars
              </p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
