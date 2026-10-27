import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: ".", testMatch: "admin-consolidation.spec.ts", timeout: 60_000, workers: 1,
  outputDir: path.resolve(__dirname, "../../artifacts/call-quality-review/admin-readiness-console-20261027/admin-browser-results"),
  use: { ...devices["Desktop Chrome"], baseURL: process.env.WEB_URL || "http://127.0.0.1:3000",
    storageState: process.env.ADMIN_UI_STORAGE_STATE || "e2e/.auth/user.json", trace: "off" },
});
