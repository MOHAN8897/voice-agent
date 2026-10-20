import assert from 'node:assert/strict';
import test from 'node:test';

import {
  filterScriptVariables,
  findScriptVariableTrigger,
  getScriptVariableGroups,
  replaceScriptVariableTrigger,
  renderScriptPreview,
} from '../src/lib/studioScriptHelpers.js';

test('variable trigger recognizes a mention at the caret and ignores email addresses', () => {
  const text = 'Hello @contact.first_name';
  assert.deepEqual(findScriptVariableTrigger(text, text.length), {
    start: 6,
    end: text.length,
    query: 'contact.first_name',
  });
  assert.equal(findScriptVariableTrigger('Email me at hello@example.com', 19), null);
});

test('variable picker and @ suggestions share supported tokens and fallback syntax', () => {
  const groups = getScriptVariableGroups(true);
  const suggestions = filterScriptVariables(groups, 'contact.first_name');
  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0].token, '{{contact.first_name | there}}');
  assert.ok(filterScriptVariables(groups, 'job_title').some((item) => item.key === 'contact.job_title'));
  assert.equal(getScriptVariableGroups(false)[0].variables[0].token, '{{contact.full_name}}');
});

test('selecting a suggestion replaces only its mention and returns the new caret position', () => {
  const text = 'Hi @first_name, nice to meet you.';
  const trigger = findScriptVariableTrigger(text, text.indexOf(','));
  const firstName = getScriptVariableGroups(false)[0].variables.find((item) => item.key === 'contact.first_name');
  const result = replaceScriptVariableTrigger(text, trigger, firstName);
  assert.equal(result.text, 'Hi {{contact.first_name}}, nice to meet you.');
  assert.equal(result.cursor, 'Hi {{contact.first_name}}'.length);
});

test('script preview resolves legacy name aliases and custom fields like call rendering', () => {
  const contact = { full_name: 'A. Sai Kumar', custom_fields: { appointment_date: '2026-11-02' } };
  assert.equal(renderScriptPreview('Hello {{name}}, {{contact.full_name}}: {{contact.custom_fields.appointment_date}}', contact), 'Hello A. Sai Kumar, A. Sai Kumar: 2026-11-02');
  assert.equal(renderScriptPreview('Hello {{contact.full_name | there}}', {}), 'Hello there');
});
