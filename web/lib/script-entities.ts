export type ScriptEntities = {
  agent_name: string;
  company_name: string;
  work_scope: string;
  role: string;
  language: string;
  direction: string;
  opening_line: string;
};

export const EMPTY_SCRIPT_ENTITIES: ScriptEntities = {
  agent_name: "",
  company_name: "",
  work_scope: "",
  role: "",
  language: "",
  direction: "",
  opening_line: "",
};

const ENTITY_KEYS: (keyof ScriptEntities)[] = [
  "agent_name",
  "company_name",
  "work_scope",
  "role",
  "language",
  "direction",
  "opening_line",
];

const ENTITY_SECTION = /---\s*ENTITY TAGS\s*---[\s\S]*?(?=\n---\s*[^-\n]+\s*---|\s*$)/i;
const TAG_LINE = /^@([a-z_]+)\s*:\s*(.+)$/i;

export function parseEntityTagsFromScript(script: string): ScriptEntities {
  const out = { ...EMPTY_SCRIPT_ENTITIES };
  const block = script.match(ENTITY_SECTION);
  const chunk = block ? block[0] : script;
  for (const line of chunk.split("\n")) {
    const m = line.trim().match(TAG_LINE);
    if (!m) continue;
    const key = m[1].toLowerCase() as keyof ScriptEntities;
    if (ENTITY_KEYS.includes(key)) {
      out[key] = m[2].trim();
    }
  }
  return out;
}

export function formatEntityTagsSection(entities: ScriptEntities): string {
  const lines = [
    "--- ENTITY TAGS ---",
    "Machine-readable call entities (do not remove — used for voice opening and brain pins).",
  ];
  for (const key of ENTITY_KEYS) {
    const val = (entities[key] || "").trim();
    if (val) lines.push(`@${key}: ${val}`);
  }
  if (lines.length <= 2) return "";
  return lines.join("\n");
}

export function stripEntityTagsSection(script: string): string {
  return script.replace(ENTITY_SECTION, "").replace(/\n{3,}/g, "\n\n").trim();
}

export function applyEntityTagsToScript(script: string, entities: ScriptEntities): string {
  const body = stripEntityTagsSection(script);
  const section = formatEntityTagsSection(entities);
  if (!section) return body;
  return body ? `${section}\n\n${body}` : section;
}

export function hasScriptEntityValues(entities: Partial<ScriptEntities> | null | undefined): boolean {
  if (!entities) return false;
  return ENTITY_KEYS.some((k) => (entities[k] || "").trim().length > 0);
}

export function entityTagsPreviewLines(entities: ScriptEntities): string[] {
  return ENTITY_KEYS
    .map((k) => {
      const v = (entities[k] || "").trim();
      return v ? `@${k}: ${v}` : "";
    })
    .filter(Boolean);
}

export const ENTITY_FIELD_LABELS: Record<keyof ScriptEntities, string> = {
  agent_name: "Agent name (@agent_name)",
  company_name: "Business / company (@company_name)",
  work_scope: "Work scope (@work_scope)",
  role: "Role (@role)",
  language: "Language (@language)",
  direction: "Call direction (@direction)",
  opening_line: "Spoken opening (@opening_line)",
};
