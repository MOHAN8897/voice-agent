import { test, expect } from "@playwright/test";
import { ensureAppLogin } from "./helpers";

test.describe("Voice Agent Web UI", () => {
  test("landing page loads and links to console", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/voice agent/i);
    await expect(page.getByRole("link", { name: "Open Console" }).first()).toBeVisible();
  });

  test("business console overview loads", async ({ page }) => {
    await ensureAppLogin(page);
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  });

  test("dev login page renders", async ({ page }) => {
    await page.goto("/dev/login");
    await expect(page.getByRole("heading", { name: /Dev Portal/i })).toBeVisible();
    await expect(page.getByLabel("Username")).toBeVisible();
  });

  test("agents page loads", async ({ page }) => {
    await ensureAppLogin(page);
    await page.goto("/app/agents");
    await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();
  });

  test("benchmarks shows disabled shell", async ({ page }) => {
    await ensureAppLogin(page);
    await page.goto("/app/benchmarks");
    await expect(page.getByText("Not configured")).toBeVisible();
  });
});
