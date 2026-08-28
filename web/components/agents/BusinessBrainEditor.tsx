"use client";

import { useCallback, useEffect, useState } from "react";
import { BrainDualPanel } from "@/components/agents/brain/BrainDualPanel";
import { BrainSectionModule } from "@/components/agents/brain/BrainSectionModule";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoStatusLight } from "@/components/ui/skeuo/SkeuoStatusLight";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import type { BrainSection, ValidationIssue } from "@/lib/brain-utils";
import { overallCompletion } from "@/lib/brain-utils";

type PublishedRecord = {
  version_id?: string;
  optimized_prompt?: string;
  optimizer_report?: { optimizer_model?: string };
  source_checksum?: string;
};

export function BusinessBrainEditor({
  agentId,
  initialSections,
  published,
  versionsCount = 0,
  initialChecksum,
  showCompiledPreview = false,
}: {
  agentId: string;
  initialSections: BrainSection[];
  published?: PublishedRecord | null;
  versionsCount?: number;
  initialChecksum?: string;
  showCompiledPreview?: boolean;
}) {
  const [sections, setSections] = useState<BrainSection[]>(initialSections);
  const [status, setStatus] = useState("");
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [optimizedPreview, setOptimizedPreview] = useState<string | null>(
    published?.optimized_prompt ?? null
  );
  const [publishedVersion, setPublishedVersion] = useState<string | null>(published?.version_id ?? null);
  const [rawChecksum, setRawChecksum] = useState(initialChecksum || "");
  const [optimizerModel, setOptimizerModel] = useState(published?.optimizer_report?.optimizer_model || "");
  const [busy, setBusy] = useState<string | null>(null);

  const completion = overallCompletion(sections);
  const validationOk = issues.length === 0;

  useEffect(() => {
    refreshPortalSession("app");
  }, []);

  function updateText(sectionId: string, raw_text: string) {
    setSections((prev) => prev.map((s) => (s.section_id === sectionId ? { ...s, raw_text } : s)));
  }

  const save = useCallback(async () => {
    setBusy("save");
    setStatus("Saving draft…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/draft`, {
      method: "PUT",
      body: JSON.stringify({ sections }),
    });
    if (r.ok) {
      const j = await r.json();
      setRawChecksum(j.raw_checksum || "");
      setStatus("Draft saved");
    } else {
      setStatus("Save failed");
    }
    setBusy(null);
  }, [agentId, sections]);

  const validate = useCallback(async () => {
    setBusy("validate");
    setStatus("Validating…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/validate`, { method: "POST" });
    if (r.ok) {
      const j = await r.json();
      setIssues(j.issues || []);
      setStatus(j.ok ? "Validation passed" : "Validation found issues");
    } else {
      setStatus("Validation request failed");
    }
    setBusy(null);
  }, [agentId]);

  const optimize = useCallback(async () => {
    setBusy("optimize");
    setStatus("Optimizing…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/optimize`, { method: "POST" });
    if (r.ok) {
      const j = await r.json();
      const opt = j.optimizer || {};
      setOptimizedPreview(opt.optimized_business_prompt || null);
      setOptimizerModel(opt.optimizer_model || "");
      setRawChecksum(j.raw_checksum || rawChecksum);
      setStatus("Optimizer preview ready — source unchanged");
    } else {
      setStatus("Optimize failed");
    }
    setBusy(null);
  }, [agentId, rawChecksum]);

  const publish = useCallback(async () => {
    setBusy("publish");
    setStatus("Publishing…");
    const r = await portalFetch("app", `/api/agents/${agentId}/business-brain/publish`, { method: "POST" });
    if (r.ok) {
      const j = await r.json();
      setPublishedVersion(j.compiled_version || publishedVersion);
      setStatus(`Published · compiled ${j.compiled_version || "—"}`);
    } else {
      setStatus("Publish failed — check validation and stack");
    }
    setBusy(null);
  }, [agentId, publishedVersion]);

  return (
    <div className="space-y-6">
      <div className="skeuo-panel rounded-skeuo-lg border border-surface-border-subtle p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="label-caps text-accent-primary">Programmable instrument</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-text">Business Brain</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-muted">
              Eight structured modules compile into one versioned prompt. Raw user source never overwrites optimized
              output.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <SkeuoButton variant="secondary" size="sm" onClick={save} loading={busy === "save"}>
              Save draft
            </SkeuoButton>
            <SkeuoButton variant="metal" size="sm" onClick={validate} loading={busy === "validate"}>
              Validate
            </SkeuoButton>
            <SkeuoButton variant="metal" size="sm" onClick={optimize} loading={busy === "optimize"}>
              Optimize
            </SkeuoButton>
            <SkeuoButton variant="primary" size="sm" onClick={publish} loading={busy === "publish"}>
              Publish
            </SkeuoButton>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4">
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Completion</p>
            <p className="font-mono text-lg tabular-nums text-text">{completion}%</p>
          </div>
          <SkeuoStatusLight
            status={validationOk && issues.length === 0 ? (completion >= 70 ? "ok" : "info") : "warn"}
            label={issues.length ? `${issues.length} validation notes` : "Sections loaded"}
          />
          <SkeuoBadge tone="muted">{versionsCount} published versions</SkeuoBadge>
          {publishedVersion && <SkeuoBadge tone="warning">Active {publishedVersion}</SkeuoBadge>}
        </div>

        {status && <p className="mt-3 text-sm text-text-muted" role="status">{status}</p>}
      </div>

      <BrainDualPanel
        sections={sections}
        optimizedText={showCompiledPreview ? optimizedPreview : null}
        publishedVersion={publishedVersion}
        rawChecksum={rawChecksum}
        optimizerModel={showCompiledPreview ? optimizerModel : undefined}
        showCompiledPreview={showCompiledPreview}
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-text">Section modules</h3>
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">8 sections · collapsible</p>
        </div>
        {sections.map((section, i) => (
          <BrainSectionModule
            key={section.section_id}
            section={section}
            issues={issues}
            onChange={(text) => updateText(section.section_id, text)}
            defaultOpen={i === 0}
          />
        ))}
      </div>
    </div>
  );
}
