import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

async function service(request) {
  const source = await readFile(new URL('../src/services/agentBrain.js', import.meta.url), 'utf8');
  const mockKey = `brainRevisionMock${crypto.randomUUID().replaceAll('-', '')}`;
  globalThis[mockKey] = request;
  const isolated = source
    .replace("import { api } from './api';", `const api = { request: globalThis.${mockKey} };`)
    .replace(/import \{[\s\S]*?\} from '\.\.\/lib\/voiceStack';/, `
      const SAAS_CALLING_SCRIPT_TITLE = 'Calling script';
      const scriptVariablesSection = () => null;
      const voiceConfigSection = () => null;
    `);
  const module = await import(`data:text/javascript;base64,${Buffer.from(isolated).toString('base64')}#${mockKey}`);
  delete globalThis[mockKey];
  return module;
}

const revision = 'a'.repeat(64);
const fields = { script: 'Represent an orbital bakery.', brainRevision: revision };

test('review and save publish the exact reviewed sections with both revision preconditions', async () => {
  const calls = [];
  const sut = await service(async (method, path, body) => {
    calls.push({ method, path, body });
    if (method === 'GET') return { draft: { sections: [], revision } };
    if (path.endsWith('/preview')) return { ok: true, issues: [] };
    if (method === 'PUT') return { revision: 'b'.repeat(64) };
    return { compiled_version: 'cb-reviewed' };
  });
  await sut.reviewAgentBrain('synthetic-agent', fields);
  const result = await sut.saveAndPublishAgentBrain('synthetic-agent', fields);
  assert.equal(calls.length, 4);
  assert.equal(calls[2].body.sections, calls[1].body.sections);
  assert.equal(calls[2].body.expected_revision, revision);
  assert.equal(calls[3].body.expected_revision, 'b'.repeat(64));
  assert.equal(result.draft_revision, 'b'.repeat(64));
});

test('a stale loaded editor cannot replace a newer draft during review or save', async () => {
  const calls = [];
  const sut = await service(async (method) => {
    calls.push(method);
    return { draft: { sections: [], revision: 'c'.repeat(64) } };
  });
  await assert.rejects(sut.saveAndPublishAgentBrain('synthetic-agent', fields), /changed in another editor/);
  assert.deepEqual(calls, ['GET']);
});

test('a concurrent PUT conflict cannot proceed to publish', async () => {
  const calls = [];
  const sut = await service(async (method, path) => {
    calls.push(method);
    if (method === 'GET') return { draft: { sections: [], revision } };
    if (path.endsWith('/preview')) return { ok: true };
    throw new Error('409 draft changed');
  });
  await assert.rejects(sut.saveAndPublishAgentBrain('synthetic-agent', fields), /409/);
  assert.deepEqual(calls, ['GET', 'POST', 'PUT']);
});

test('blocking review findings prevent every draft or publication mutation', async () => {
  const calls = [];
  const sut = await service(async (method) => {
    calls.push(method);
    return method === 'GET' ? { draft: { sections: [], revision } } : { ok: false, issues: [{ severity: 'blocking' }] };
  });
  await assert.rejects(sut.saveAndPublishAgentBrain('synthetic-agent', fields), /blocking script issues/);
  assert.deepEqual(calls, ['GET', 'POST']);
});
