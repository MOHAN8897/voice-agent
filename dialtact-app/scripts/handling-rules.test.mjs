import test from 'node:test';
import assert from 'node:assert/strict';
import { handlingRuleSections, storedHandlingRules } from '../src/lib/handlingRules.js';
import { parseObjectionRulesFromSections } from '../src/lib/studioScriptHelpers.js';

test('objectives and objections roundtrip multiline guidance and compile only enabled rules', () => {
  const sections = handlingRuleSections([
    { kind: 'objective', trigger: 'Interested\nAsk about timing', response: 'Explain first.\nCapture preference.', action: 'offer_callback' },
    { kind: 'objection', trigger: 'తెలుగు ప్రశ్న', response: 'వివరాలు చెప్పాలి', action: 'continue_script' },
    { kind: 'objective', trigger: 'Disabled goal', response: 'Do not compile me.', enabled: false },
  ]);
  const restored = storedHandlingRules(sections);
  assert.equal(restored[0].response, 'Explain first.\nCapture preference.');
  assert.equal(restored[2].enabled, false);
  assert.deepEqual(parseObjectionRulesFromSections(sections), restored);
  assert.match(sections[1].raw_text, /\[Objective\]/);
  assert.match(sections[1].raw_text, /వివరాలు చెప్పాలి/);
  assert.doesNotMatch(sections[1].raw_text, /Do not compile me/);
});

test('clearing rules is explicit and invalid rules block publication', () => {
  assert.deepEqual(parseObjectionRulesFromSections(handlingRuleSections([])), []);
  assert.equal(handlingRuleSections([])[1].enabled, false);
  assert.throws(() => handlingRuleSections([{ trigger: 'price', response: '' }]), /Complete/);
  assert.throws(() => handlingRuleSections([{ kind: 'override-system', trigger: 'x', response: 'y' }]), /Review/);
  assert.throws(() => storedHandlingRules([{ title: 'saas_handling_rules', raw_text: '{broken' }]), /could not be read/);
  assert.throws(() => storedHandlingRules([{ title: 'saas_handling_rules', raw_text: 'null' }]), /unsupported/);
  assert.throws(() => handlingRuleSections([null]), /Review handling rule/);
});
