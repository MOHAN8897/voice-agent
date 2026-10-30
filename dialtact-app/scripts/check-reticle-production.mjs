import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

async function listFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? listFiles(target) : [target];
  }));
  return nested.flat();
}

const distRoot = fileURLToPath(new URL('../dist/', import.meta.url));
const files = await listFiles(distRoot);
const reticleMarkers = [
  '@reticlehq/react',
  '@reticlehq/vite-plugin',
  '__RETICLE_ROOT__',
  'reticle:hydration-complete',
];
const leakedFiles = [];

for (const file of files) {
  const contents = await readFile(file, 'utf8');
  if (reticleMarkers.some((marker) => contents.includes(marker))) {
    leakedFiles.push(path.relative(distRoot, file));
  }
}

assert.deepEqual(leakedFiles, [], `Reticle development code leaked into production output: ${leakedFiles.join(', ')}`);
console.log('Production output contains no Reticle development runtime.');
