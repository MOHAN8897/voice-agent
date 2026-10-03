/**
 * Guards against the landing page regressing into what it was.
 *
 * The copy problems this file exists to catch were all *invisible* — a build passed, a
 * screenshot looked fine, and the page still said four different things about the same
 * number. So they are checked by reading the rendered output, not by eyeballing the JSX.
 *
 * Run with:  node scripts/check-landing-copy.mjs
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, '..', 'src');
const COMPONENTS = join(SRC, 'components');

/** Strip comments so the file's own explanations of the old copy do not trip the checks. */
function stripComments(code) {
  return code.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

function componentFiles() {
  return readdirSync(COMPONENTS)
    .filter((f) => f.endsWith('.jsx') || f.endsWith('.js'))
    .map((f) => join(COMPONENTS, f));
}

const failures = [];
const rendered = componentFiles()
  .map((f) => ({ file: f, code: stripComments(readFileSync(f, 'utf8')) }))
  .map(({ file, code }) => ({ file: `${file.split(/[\\/]/).pop()}`, code }))
  .filter(({ file }) => file !== 'App.jsx'); // App.jsx only wires sections up

const siteContent = stripComments(readFileSync(join(SRC, 'data', 'siteContent.js'), 'utf8'));
const allRendered = siteContent + '\n' + rendered.map((r) => r.code).join('\n');

function countOf(pattern) {
  const matches = allRendered.match(new RegExp(pattern, 'g'));
  return matches ? matches.length : 0;
}

// 1. A number said once. Each of these used to appear 2-5 times in different versions.
const SAID_ONCE = [
  ['latency claim (ms)', /\b\d{2,4}\s?ms\b|sub-\d{3}\s?ms|ultra-low \d{3}ms/gi, 1],
  ['the "4.2x" speedup', /4\.2x/g, 0],
  ['"40+ voices"', /40\+[a-z ]*voice/gi, 0],
  ['"100,000 concurrent"', /100,000/g, 0],
];

for (const [label, pattern, max] of SAID_ONCE) {
  const n = countOf(pattern.source ?? pattern);
  if (n > max) failures.push(`${label}: expected at most ${max} mention(s), found ${n}`);
}

// 2. Guarantees and absolute claims. A wrong promise is the one thing a buyer cannot
//    negotiate with later.
const FORBIDDEN = [
  ['zero hallucination guarantee', /zero[- ]hallucination|100%\s*(grounded|field accuracy|compliance|combinatorial)/i],
  ['guaranteed outcome', /guarantee[sd]?\b/i],
  ['unsourced performance figure', /\+?3[0-9]%|94% inquiry|\$140k|26\.4%|12,482|4\.9\/5|4\.8\/5/],
  ['carrier name in customer copy', /\bTelnyx\b|\bTwilio\b|\bPlivo\b/],
  ['fake live-telemetry signal', /updated \d+s ago/i],
];

for (const [label, pattern] of FORBIDDEN) {
  const hits = rendered.filter((r) => pattern.test(r.code));
  for (const h of hits) {
    failures.push(`${label} still present in ${h.file}`);
  }
}

// 3. Section integrity: every nav anchor must exist, and no section may be imported
//    twice (a section rendered twice is a section saying itself twice).
const app = readFileSync(join(SRC, 'App.jsx'), 'utf8');
const content = readFileSync(join(SRC, 'data', 'siteContent.js'), 'utf8');

const navMatch = content.match(/export const NAV_LINKS = \[([\s\S]*?)\];/);
const anchors = navMatch ? [...navMatch[1].matchAll(/href: '#([^']+)'/g)].map((m) => m[1]) : [];
for (const anchor of anchors) {
  const defined = readFileSync(join(SRC, 'App.jsx'), 'utf8').includes(`id="${anchor}"`)
    || componentFiles().some((f) => readFileSync(f, 'utf8').includes(`id="${anchor}"`));
  if (!defined) failures.push(`nav link "#${anchor}" has no matching section id`);
}

const sectionImports = [...app.matchAll(/^import \{ (\w+) \} from '\.\/components\/(\w+)';/gm)];
const seen = new Map();
for (const [, name, file] of sectionImports) {
  if (seen.has(file)) failures.push(`component ${file} is imported twice`);
  seen.set(file, name);
}

// 4. Dead content: an export nobody imports is a claim nobody sees and nobody maintains.
const exported = [...content.matchAll(/export const (\w+)/g)].map((m) => m[1]);
const consumers = componentFiles().map((f) => readFileSync(f, 'utf8')).join('\n') + app;
for (const name of exported) {
  if (!consumers.includes(name)) failures.push(`siteContent exports "${name}" but nothing imports it`);
}

if (failures.length) {
  console.error('Landing copy checks failed:\n');
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}

console.log(
  `Landing copy OK — ${anchors.length} nav anchors resolve, ${exported.length} content exports all used, ` +
    `no repeated numbers, no guarantees, no carrier names.`
);
