import { defineConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');

const baseURL = process.env.VOXLY_BASE_URL || 'http://127.0.0.1:5173';
const apiURL = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './e2e',
  // This file is a standalone contract runner with process.exit(), not a Playwright spec.
  testIgnore: ['**/backend-contract.spec.js', '**/admin-live-transcription.spec.js'],
  // Admin transcription has its own isolated Next/API harness in e2e/admin-transcription.config.js.
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : [
        {
          command: 'python -m uvicorn server.app:app --host 127.0.0.1 --port 8000',
          cwd: repoRoot,
          url: `${apiURL}/api/health`,
          reuseExistingServer: true,
          timeout: 120_000,
        },
        {
          command: 'npm run dev -- --host 127.0.0.1 --port 5173',
          cwd: __dirname,
          url: baseURL,
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
});
