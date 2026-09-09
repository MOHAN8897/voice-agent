/**
 * Test Studio mode switching + usage panel E2E.
 * Run: PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test e2e/test-studio-modes.spec.ts --workers=1
 */
import { test, expect } from "@playwright/test";
import { ensureDevPortalReady } from "./helpers";

async function defaultAgentId(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const r = await request.get("/api/agents");
  expect(r.ok()).toBeTruthy();
  const id = (await r.json()).agents?.[0]?.agent_id as string | undefined;
  if (!id) throw new Error("No agents available");
  return id;
}

async function waitForTestStudioReady(page: import("@playwright/test").Page) {
  await ensureDevPortalReady(page);
  await expect(page.getByTestId("test-studio-mode-picker")).toBeVisible({ timeout: 30000 });
  await page.waitForResponse(
    (r) => r.url().includes("/api/test-studio/prefs") && r.request().method() === "GET",
    { timeout: 15000 }
  ).catch(() => {});
}
async function openTestStudio(
  page: import("@playwright/test").Page,
  opts?: { channel?: "agent" | "pstn" }
) {
  const channel = opts?.channel ?? "agent";
  const agentId = await defaultAgentId(page.request);
  await page.goto(`/dev/test-studio/${agentId}`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await waitForTestStudioReady(page);
  await page.getByTestId(`test-mode-${channel}`).click();
  if (channel === "agent") {
    await expect(page.getByLabel(/Turn microphone on/i)).toBeVisible({ timeout: 15000 });
  } else {
    await expect(page.getByRole("heading", { name: /^PSTN · / })).toBeVisible({ timeout: 20000 });
  }
}

test.describe("Test Studio modes", () => {
  test.describe.configure({ mode: "serial" });

  test("defaults to Agent only with mic and usage panel", async ({ page }) => {
    await openTestStudio(page, { channel: "agent" });
    await expect(page.getByTestId("test-mode-agent")).toBeVisible();
    await expect(page.getByTestId("test-studio-usage-panel")).toBeVisible();
    await expect(page.getByLabel(/Turn microphone on/i)).toBeVisible();
    await expect(page.getByTestId("usage-empty-hint")).toContainText(/mic on/i);
  });

  test("switches to Full PSTN and shows telephony panel", async ({ page }) => {
    await openTestStudio(page, { channel: "agent" });
    await page.getByTestId("test-mode-pstn").click();
    await expect(page.getByRole("heading", { name: /^PSTN · / })).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("heading", { name: "Outbound test call" })).toBeVisible({ timeout: 20000 });
    await expect(page.getByLabel(/Turn microphone on/i)).not.toBeVisible();
    await expect(page.getByTestId("usage-empty-hint")).toContainText(/Agent only mode/i);
  });

  test("switches back to Agent only from PSTN", async ({ page }) => {
    await openTestStudio(page, { channel: "pstn" });
    await page.getByTestId("test-mode-agent").click();
    await expect(page.getByLabel(/Turn microphone on/i)).toBeVisible();
    await expect(page.getByText("Live conversation")).toBeVisible();
  });

  test("usage panel shows STT LLM TTS section labels", async ({ page }) => {
    await openTestStudio(page, { channel: "agent" });
    const panel = page.getByTestId("test-studio-usage-panel");
    await expect(panel.getByText("STT chars", { exact: true })).toBeVisible();
    await expect(panel.getByText("LLM in", { exact: true })).toBeVisible();
    await expect(panel.getByText("TTS chars", { exact: true })).toBeVisible();
    await expect(panel.getByText("Session totals")).toBeVisible();
  });

  test("config channel tab mirrors agent / pstn labels", async ({ page }) => {
    await openTestStudio(page, { channel: "agent" });
    await page.getByRole("button", { name: /^Config\b/i }).click();
    await page.getByRole("button", { name: /^Channel$/i }).click();
    await expect(page.getByTestId("config-channel-agent")).toBeVisible();
    await expect(page.getByTestId("config-channel-pstn")).toBeVisible();
    await expect(page.getByText(/Agent only tests STT/i)).toBeVisible();
  });
});
