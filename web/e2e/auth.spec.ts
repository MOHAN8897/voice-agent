import { test, expect } from "@playwright/test";

test.describe("Tier 2 — Auth pages (PRD §4)", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("business login page has accessible form", async ({ page }) => {
    await page.goto("/app/login");
    await expect(page.getByRole("heading", { name: /Sign in/i })).toBeVisible();
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("dev login page has accessible form", async ({ page }) => {
    await page.goto("/dev/login");
    await expect(page.getByRole("heading", { name: /Dev Portal/i })).toBeVisible();
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("access denied page renders", async ({ page }) => {
    await page.goto("/app/access-denied");
    await expect(page.getByRole("heading", { name: /Access denied/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Switch tenant/i })).toBeVisible();
  });

  test("tenant selector renders workspaces", async ({ page }) => {
    await page.goto("/app/select-tenant");
    await expect(page.getByRole("heading", { name: /Select workspace/i })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Tenants" })).toBeVisible();
  });
});
