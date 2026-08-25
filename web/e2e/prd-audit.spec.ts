/**
 * PRD gap audit — documents expected Phase 1–5 UI vs current Next.js app.
 * Many tests intentionally fail until features are implemented.
 * Run: npm run test:e2e -- e2e/prd-audit.spec.ts
 */
import { test, expect } from "@playwright/test";
import { ensureAppLogin } from "./helpers";

test.describe("PRD §3 Primary navigation (prd/11)", () => {
  const requiredNav = [
    "Overview",
    "Agents",
    "Test Studio",
    "Calls",
    "Analytics",
    "Benchmarks",
    "Providers",
    "Integrations",
    "Settings",
  ];

  test.beforeEach(async ({ page }, testInfo) => {
    if (!testInfo.title.includes("sign-in")) {
      await ensureAppLogin(page);
    }
    await page.goto("/app");
  });

  for (const label of requiredNav) {
    test(`nav includes: ${label}`, async ({ page }) => {
      await expect(page.getByRole("link", { name: label, exact: true })).toBeVisible();
    });
  }
});

async function defaultAgentId(page: import("@playwright/test").Page): Promise<string> {
  const r = await page.request.get("/api/agents");
  const j = await r.json();
  const id = j.agents?.[0]?.agent_id as string | undefined;
  if (!id) throw new Error("No agents seeded — start API with Postgres");
  return id;
}

test.describe("PRD Agent workspace routes (phase-02/05)", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppLogin(page);
  });

  test("agent has summary workspace tab", async ({ page }) => {
    const agentId = await defaultAgentId(page);
    await page.goto(`/app/agents/${agentId}/summary`);
    await expect(page.getByRole("heading", { name: /Summary/i })).toBeVisible();
  });

  test("agent has 8-section Business Brain editor", async ({ page }) => {
    const agentId = await defaultAgentId(page);
    await page.goto(`/app/agents/${agentId}/brain`);
    await expect(page.getByText("Identity & Purpose")).toBeVisible();
    await expect(page.getByText("Facts")).toBeVisible();
    await expect(page.getByText("Guardrails")).toBeVisible();
  });
});

test.describe("PRD Test Studio live voice (phase-05 §4.3)", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppLogin(page);
  });

  test("live session has mic / listening controls", async ({ page }) => {
    const agentId = await defaultAgentId(page);
    await page.goto(`/app/agents/${agentId}/test`);
    await expect(page.getByRole("button", { name: /Start listening|Start mic|Hands-free/i })).toBeVisible();
  });

  test("live session shows transcript bubbles not textarea-only", async ({ page }) => {
    const agentId = await defaultAgentId(page);
    await page.goto(`/app/agents/${agentId}/test`);
    await expect(page.getByRole("region", { name: /transcript/i })).toBeVisible();
  });
});

test.describe("PRD Calls detail (phase-03/05)", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAppLogin(page);
  });

  test("call detail loads transcript timeline from API", async ({ page }) => {
    await page.goto("/app/calls");
    const row = page.locator("table tbody tr, ul li a").first();
    if (await row.count() === 0) {
      test.skip();
    }
    await row.click();
    await expect(page.getByRole("heading", { name: /Transcript/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Play|Audio/i })).toBeVisible();
  });
});

test.describe("PRD Dev Portal (phase-05 §6.3)", () => {
  test("dev stack has tier editor not JSON dump only", async ({ page }) => {
    await page.goto("/dev/stack");
    await expect(page.getByRole("button", { name: /Update tier/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Promote/i })).toBeVisible();
  });

  test("dev portal has platform brain route", async ({ page }) => {
    await page.goto("/dev/platform-brain");
    await expect(page.getByRole("heading", { name: /Platform Brain/i })).toBeVisible();
  });
});

test.describe("PRD Auth (phase-05 §6.1)", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("business console requires sign-in", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: /Sign in|Log in/i })).toBeVisible();
  });
});
