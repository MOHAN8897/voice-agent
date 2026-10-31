import assert from 'node:assert/strict';
import test from 'node:test';

import { initializeGoogleIdentityOnce } from '../src/utils/loadGoogleIdentity.js';

test('Google Identity initializes once and uses the latest credential handler', () => {
  const key = Symbol.for('dialtact.googleIdentityState');
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    google: {
      accounts: {
        id: {
          initialize: (options) => calls.push(options),
        },
      },
    },
  };

  try {
    const firstHandler = () => 'first';
    const latestHandler = () => 'latest';
    assert.equal(initializeGoogleIdentityOnce('client-id', firstHandler), true);
    assert.equal(initializeGoogleIdentityOnce('client-id', latestHandler), true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].client_id, 'client-id');
    assert.equal(calls[0].callback({}), 'latest');
    assert.equal(initializeGoogleIdentityOnce('different-client-id', firstHandler), false);
  } finally {
    delete globalThis.window[key];
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }
});
