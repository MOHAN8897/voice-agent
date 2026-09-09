#!/usr/bin/env node
/**
 * Windows fix for @nanonets/graft: tree-sitter-kotlin has no win32 prebuild
 * for Node 22, and Graft eagerly imports it. Stub the binding so Python/TS
 * indexing works. Safe to re-run after `npm install -g @nanonets/graft`.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

function findGraftRoot() {
  try {
    return dirname(require.resolve("@nanonets/graft/package.json"));
  } catch {
    const globalPath = join(
      process.env.APPDATA || "",
      "npm",
      "node_modules",
      "@nanonets",
      "graft",
    );
    if (existsSync(join(globalPath, "package.json"))) return globalPath;
    throw new Error("@nanonets/graft not found — run: npm install -g @nanonets/graft --ignore-scripts");
  }
}

const root = findGraftRoot();
const kotlinIdx = join(root, "node_modules", "tree-sitter-kotlin", "bindings", "node", "index.js");
const extractJs = join(root, "dist", "graph", "extract.js");

if (existsSync(kotlinIdx)) {
  writeFileSync(
    kotlinIdx,
    `// Windows stub — no win32 prebuild for tree-sitter-kotlin on Node 22.\nmodule.exports = null;\n`,
    "utf8",
  );
  console.log("✓ stubbed tree-sitter-kotlin");
}

if (existsSync(extractJs)) {
  let src = readFileSync(extractJs, "utf8");
  let changed = false;
  if (!src.includes("kotlin: Kotlin || undefined") && !src.includes("kotlin: Kotlin||undefined")) {
    src = src.replace(/kotlin:\s*Kotlin,/, "kotlin: Kotlin || undefined,");
    changed = true;
  }
  if (!src.includes("if (!GRAMMARS[lang])")) {
    src = src.replace(
      /export function extractFile\(rel, source, lang\) \{\s*parser\.setLanguage\(GRAMMARS\[lang\]\);/,
      'export function extractFile(rel, source, lang) {\n    if (!GRAMMARS[lang]) throw new Error("grammar unavailable: " + lang);\n    parser.setLanguage(GRAMMARS[lang]);',
    );
    changed = true;
  }
  if (changed) {
    writeFileSync(extractJs, src, "utf8");
    console.log("✓ patched extract.js for null grammars");
  } else {
    console.log("· extract.js already patched");
  }
}

console.log(`Graft root: ${root}`);
console.log("Done. Run: graft --version && graft build");
