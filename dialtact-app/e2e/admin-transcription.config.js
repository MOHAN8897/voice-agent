import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'admin-live-transcription.spec.js', timeout: 90000,
  workers: 1, use: { trace: 'on-first-retry' },
  webServer: [
    { command: 'node e2e/fixtures/admin-api-stub.mjs', cwd: '..', url: 'http://127.0.0.1:8018/api/auth/dev-me', reuseExistingServer: false },
    { command: 'npm run dev -- --hostname 127.0.0.1 --port 3012', cwd: '../../web',
      env: { NEXT_DIST_DIR: '.next-transcription-audit', API_INTERNAL_URL: 'http://127.0.0.1:8018' },
      url: 'http://127.0.0.1:3012/dev/login', reuseExistingServer: false, timeout: 120000 },
  ],
});
