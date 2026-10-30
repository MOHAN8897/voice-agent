import test from 'node:test';
import assert from 'node:assert/strict';
import { UNSOURCED_PERFORMANCE_PATTERN } from './check-landing-copy.mjs';

test('unsourced performance copy remains blocked without treating CSS gradient stops as claims', () => {
  for (const claim of ['+34% pipeline uplift', '34% conversion growth', '4.9/5', '94% inquiry capture']) assert.match(claim, UNSOURCED_PERFORMANCE_PATTERN);
  assert.doesNotMatch('radial-gradient(120% 90% at 20% 0%, #000 30%, transparent 78%)', UNSOURCED_PERFORMANCE_PATTERN);
});
