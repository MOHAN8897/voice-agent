import { defineConfig, devices } from "@playwright/test";

const API_URL = process.env.API_URL || "http://localhost:8000";
const WEB_URL = process.env.WEB_URL || "http://localhost:3000";
const skipWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: process.env.CI ? 1 : 2,
  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
      testIgnore: /auth\.setup\.ts/,
    },
  ],
  webServer: skipWebServer
    ? undefined
    : [
    {
      command: "python -m uvicorn server.app:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: `${API_URL}/api/health`,
      reuseExistingServer: true,
      timeout: 120000,
      env: {
        ...process.env,
        APP_CONSOLE_USERNAME: "e2e",
        APP_CONSOLE_PASSWORD: "e2e-test",
      },
    },
    {
      command: "npm run dev",
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 120000,
    },
  ],
});
