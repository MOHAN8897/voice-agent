import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".", testMatch: "billing-stack.spec.ts", timeout: 60_000, workers: 1,
  outputDir: "../../artifacts/call-quality-review/billing-layout-conversion-20261027/admin-browser-results",
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3000",
    storageState: "e2e/.auth/user.json", trace: "off" },
});
