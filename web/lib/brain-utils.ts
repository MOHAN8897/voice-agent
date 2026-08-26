/** Business brain section helpers — completion & assembly preview */
import { BRAIN_SECTION_ORDER } from "@/lib/constants";

export type BrainSection = {
  section_id: string;
  type: string;
  title: string;
  raw_text: string;
  order: number;
  enabled: boolean;
};

export type ValidationIssue = {
  severity: string;
  code: string;
  message: string;
  section_ids: string[];
};

const SECTION_MAX_CHARS = 8000;
const MIN_CHARS_COMPLETE = 40;

export function sectionCompletion(section: BrainSection): number {
  if (!section.enabled) return 100;
  const text = (section.raw_text || "").trim();
  if (!text) return 0;
  const ratio = Math.min(1, text.length / MIN_CHARS_COMPLETE);
  return Math.round(30 + ratio * 70);
}

export function overallCompletion(sections: BrainSection[]): number {
  const enabled = sections.filter((s) => s.enabled);
  if (!enabled.length) return 0;
  const sum = enabled.reduce((acc, s) => acc + sectionCompletion(s), 0);
  return Math.round(sum / enabled.length);
}

export function assembleRawPreview(sections: BrainSection[]): string {
  const enabled = sections
    .filter((s) => s.enabled)
    .sort((a, b) => a.order - b.order);
  return enabled
    .map((s) => `<!-- ${s.type} -->\n${s.raw_text || ""}`)
    .join("\n\n");
}

export function charLimitFor(section: BrainSection): number {
  return SECTION_MAX_CHARS;
}

export function orderBrainSections(sections: BrainSection[]): BrainSection[] {
  const ordered = BRAIN_SECTION_ORDER.map((type) => sections.find((s) => s.type === type)).filter(
    Boolean
  ) as BrainSection[];
  const extras = sections.filter((s) => !BRAIN_SECTION_ORDER.includes(s.type as typeof BRAIN_SECTION_ORDER[number]));
  return [...ordered, ...extras];
}

export function issuesForSection(issues: ValidationIssue[], sectionId: string): ValidationIssue[] {
  return issues.filter((i) => i.section_ids?.includes(sectionId));
}
