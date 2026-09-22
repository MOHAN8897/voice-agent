import { defineConfig } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');

const baseURL = process.env.VOXLY_BASE_URL || 'http://127.0.0.1:5173';
const apiURL = process.env.VOXLY_API_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './e2e',
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
