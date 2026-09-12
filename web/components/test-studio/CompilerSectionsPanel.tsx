"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/cn";

export type CompilerSection = {
  id: string;
  title: string;
  description: string;
  editable: boolean;
  cached: boolean;
  text: string;
};

export type CompilerSectionsPayload = {
  sections: CompilerSection[];
  fullCompiled: string;
  tokenEstimate: number;
  compilerVersion?: string;
};

type Props = {
  data: CompilerSectionsPayload | null;
  className?: string;
};

export function CompilerSectionsPanel({ data, className }: Props) {
  const [openId, setOpenId] = useState<string>("user_script");
  const sections = useMemo(() => data?.sections ?? [], [data]);

  if (!data || !sections.length) {
    return (
      <div className={cn("rounded-skeuo-sm border border-surface-border-subtle p-4 text-sm text-text-muted", className)}>
        Create agent script to view compiler sections sent to the Realtime cache.
      </div>
    );
  }

  return (
    <div className={cn("rounded-skeuo-sm border border-surface-border-subtle p-4", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-text">Compiler sections (Realtime cache)</p>
          <p className="mt-0.5 text-[11px] text-text-subtle">
            User-facing script vs system layers assembled into the cached brain prompt.
          </p>
        </div>
        <dl className="flex gap-4 text-[11px] text-text-muted">
          <div>
            <dt className="inline">Version </dt>
            <dd className="inline font-mono text-text">{data.compilerVersion || "—"}</dd>
          </div>
          <div>
            <dt className="inline">Est. tokens </dt>
            <dd className="inline font-mono text-text">{data.tokenEstimate ?? "—"}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-4 space-y-2">
        {sections.map((section) => {
          const open = openId === section.id;
          return (
            <div key={section.id} className="rounded-lg border border-surface-border-subtle overflow-hidden">
              <button
                type="button"
                className="flex w-full items-start justify-between gap-3 px-3 py-2 text-left hover:bg-surface-raised/60"
                onClick={() => setOpenId(open ? "" : section.id)}
              >
                <span>
                  <span className="text-sm font-medium text-text">{section.title}</span>
                  <span className="ml-2 text-[10px] uppercase tracking-wide text-text-subtle">
                    {section.editable ? "editable" : "system"}
                  </span>
                  <p className="mt-0.5 text-[11px] text-text-muted">{section.description}</p>
                </span>
                <span className="text-xs text-text-subtle">{open ? "−" : "+"}</span>
              </button>
              {open ? (
                <pre className="max-h-64 overflow-auto border-t border-surface-border-subtle bg-surface-raised/40 p-3 font-mono text-[11px] text-text-muted whitespace-pre-wrap">
                  {section.text || "(empty)"}
                </pre>
              ) : null}
            </div>
          );
        })}
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-medium text-text-muted">Full compiled brain</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-surface-raised p-3 font-mono text-[10px] text-text-muted whitespace-pre-wrap">
          {data.fullCompiled || "(empty)"}
        </pre>
      </details>
    </div>
  );
}
