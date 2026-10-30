import { defineConfig, devices } from "@playwright/test";

// Mocked-API harness for the Number purchases admin page: point the Next dev
// server's API_INTERNAL_URL at a closed port so the session middleware falls
// back to the cookie, and the browser routes every /api call to fixtures.
export default defineConfig({
  testDir: ".",
  testMatch: "admin-number-purchases.spec.ts",
  timeout: 90_000,
  workers: 1,
  outputDir: process.env.PW_OUTPUT_DIR || "test-results/admin-number-purchases",
  use: { ...devices["Desktop Chrome"], baseURL: process.env.WEB_URL || "http://127.0.0.1:3391", trace: "off" },
});
