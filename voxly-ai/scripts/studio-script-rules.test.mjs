import test from 'node:test';
import assert from 'node:assert/strict';
import {
  renderScriptPreview,
  OBJECTION_PRESETS,
  SAMPLE_LEADS,
  parseObjectionRulesFromSections,
} from '../src/lib/studioScriptHelpers.js';

test('renderScriptPreview resolves contact fields and fallback defaults', () => {
  const completeLead = SAMPLE_LEADS[0].contact;
  const sparseLead = SAMPLE_LEADS[1].contact;

  const template = 'Hello {{contact.first_name | there}}, calling from {{contact.company | our enterprise team}} about {{contact.custom_fields.product | our AI solution}}.';

  const renderedComplete = renderScriptPreview(template, completeLead);
  assert.equal(renderedComplete.includes('Hello Priya'), true);
  assert.equal(renderedComplete.includes('Apex Technologies'), true);
  assert.equal(renderedComplete.includes('Voice Agent AI Pro'), true);

  const renderedSparse = renderScriptPreview(template, sparseLead);
  assert.equal(renderedSparse.includes('Hello there'), true);
  assert.equal(renderedSparse.includes('our enterprise team'), true);
  assert.equal(renderedSparse.includes('our AI solution'), true);
});

test('renderScriptPreview resolves dynamic system context tokens', () => {
  const template = 'Good {{system.time_of_day}}! Today is {{system.day_of_week}} and the date is {{system.date}}.';
  const rendered = renderScriptPreview(template, {});

  assert.equal(/Good (morning|afternoon|evening)!/.test(rendered), true);
  assert.equal(/Today is (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)/.test(rendered), true);
  assert.equal(rendered.includes('{{system.'), false);
});

test('OBJECTION_PRESETS provide compliant behavioral action outcomes', () => {
  assert.equal(OBJECTION_PRESETS.length >= 5, true);
  const categories = OBJECTION_PRESETS.map((p) => p.category);
  assert.equal(categories.includes('price'), true);
  assert.equal(categories.includes('timing'), true);
  assert.equal(categories.includes('trust'), true);
  assert.equal(categories.includes('competitor'), true);
  assert.equal(categories.includes('not_interested'), true);

  // Check actions align with STATIC_OUTPUT_RULES
  const pricePreset = OBJECTION_PRESETS.find((p) => p.id === 'price');
  assert.equal(pricePreset.action, 'continue_script');

  const busyPreset = OBJECTION_PRESETS.find((p) => p.id === 'busy');
  assert.equal(busyPreset.action, 'offer_callback');

  const notInterestedPreset = OBJECTION_PRESETS.find((p) => p.id === 'not_interested');
  assert.equal(notInterestedPreset.action, 'end_call');
});

test('parseObjectionRulesFromSections accurately parses structured FAQ sections', () => {
  const mockSections = [
    {
      type: 'faq',
      title: 'FAQ & Objections',
      enabled: true,
      raw_text: `[Intent: price]
When: Too expensive
Reply: We deliver high ROI within 30 days.
Action: continue_script

[Intent: timing]
When: Busy right now
Reply: Would tomorrow work better?
Action: offer_callback`,
    },
  ];

  const parsed = parseObjectionRulesFromSections(mockSections);
  assert.equal(parsed.length, 2);
  assert.equal(parsed[0].category, 'price');
  assert.equal(parsed[0].trigger, 'Too expensive');
  assert.equal(parsed[0].response, 'We deliver high ROI within 30 days.');
  assert.equal(parsed[0].action, 'continue_script');

  assert.equal(parsed[1].category, 'timing');
  assert.equal(parsed[1].trigger, 'Busy right now');
  assert.equal(parsed[1].response, 'Would tomorrow work better?');
  assert.equal(parsed[1].action, 'offer_callback');
});
