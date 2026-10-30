import assert from 'node:assert/strict';
import test from 'node:test';

import { isLocalReticleHost, isReticleAllowed } from '../src/services/reticleGate.js';

test('Reticle is available for authenticated local development only', () => {
  for (const hostname of ['localhost', '127.0.0.1', '::1', '[::1]', 'app.localhost']) {
    assert.equal(isLocalReticleHost(hostname), true, `${hostname} should be local`);
    assert.equal(isReticleAllowed({ isDevelopment: true, hostname, authenticated: true }), true);
  }

  for (const hostname of ['dialtact.com', 'www.dialtact.com', 'app-dev.dialtact.com', '192.168.1.10']) {
    assert.equal(isLocalReticleHost(hostname), false, `${hostname} should not be local`);
    assert.equal(isReticleAllowed({ isDevelopment: true, hostname, authenticated: true }), false);
  }

  assert.equal(isReticleAllowed({ isDevelopment: false, hostname: 'localhost', authenticated: true }), false);
  assert.equal(isReticleAllowed({ isDevelopment: true, hostname: 'localhost', authenticated: false }), false);
});
