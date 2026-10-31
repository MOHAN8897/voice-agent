/**
 * Cross-check that every test id the E2E specs reference still exists in the source.
 *
 * Cheap insurance against selectors rotting when a component is restructured.
 * Run: node scripts/check-e2e-testids.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.cwd());
const specDir = path.join(root, 'e2e');
const srcDir = path.join(root, 'src');

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(jsx?|tsx?)$/.test(entry.name)) out.push(full);
  }
  return out;
}

const source = walk(srcDir)
  .map((f) => fs.readFileSync(f, 'utf8'))
  .join('\n');

const specs = walk(specDir).filter((f) => f.endsWith('.spec.js'));
const ids = new Set();
for (const spec of specs) {
  const text = fs.readFileSync(spec, 'utf8');
  for (const m of text.matchAll(/getByTestId\(\s*[`'"]([^`'"$]+)[`'"]/g)) {
    ids.add(m[1]);
  }
}

// Ids built by interpolation, e.g. `calls-status-${bucket}`.
const patterns = new Set();
for (const m of source.matchAll(/data-testid=\{`([^`]+)`\}/g)) {
  patterns.add(m[1].replace(/\$\{[^}]+\}/g, '*'));
}

/** Does a concrete id match a template like `employee-mode-*`? */
function matchesTemplate(id, template) {
  const re = new RegExp(
    `^${template
      .split('*')
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .join('.*')}$`
  );
  return re.test(id);
}

const missing = [];
for (const id of ids) {
  if (source.includes(id)) continue;
  if ([...patterns].some((p) => matchesTemplate(id, p))) continue;
  missing.push(id);
}

console.log(`spec files      : ${specs.length}`);
console.log(`test ids used   : ${ids.size}`);
console.log(`templated ids   : ${patterns.size}`);
console.log(
  missing.length ? `\nMISSING (${missing.length}):\n  ${missing.join('\n  ')}` : '\nAll referenced test ids exist.'
);
process.exit(missing.length ? 1 : 0);
