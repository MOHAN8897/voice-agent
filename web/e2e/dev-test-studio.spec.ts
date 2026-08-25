/**
 * Dev Test Studio E2E — UI load, catalog arrays, call lifecycle API.
 * Run: PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:e2e -- e2e/dev-test-studio.spec.ts
 */
import { test, expect } from "@playwright/test";

const DEV_USER = { username: "dev", password: "devpass" };

async function ensureDevLogin(page: import("@playwright/test").Page) {
  const login = await page.request.post("/api/dev/login", { data: DEV_USER });
  expect(login.ok()).toBeTruthy();
}

async function defaultAgentId(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const r = await request.get("/api/agents");
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  const id = j.agents?.[0]?.agent_id as string | undefined;
  if (!id) throw new Error("No agents available");
  return id;
}

test.describe("Dev Test Studio API", () => {
  test("catalog voicePresets is an array (no .map crash)", async ({ request }) => {
    const r = await request.get("/api/settings/catalog");
    expect(r.ok()).toBeTruthy();
    const presets = (await r.json()).tts?.voicePresets;
    expect(Array.isArray(presets)).toBeTruthy();
    expect(presets.length).toBeGreaterThan(0);
  });

  test("agent slug default resolves", async ({ request }) => {
    const r = await request.get("/api/agents/default");
    expect(r.ok()).toBeTruthy();
    const agent = (await r.json()).agent;
    expect(agent.name).toBe("default");
    expect(agent.agent_id).toBeTruthy();
  });

  test("call lifecycle start and end via API", async ({ request }) => {
    const agentId = await defaultAgentId(request);
    const start = await request.post("/api/call/start", {
      data: { agentId, channel: "browser", direction: "inbound", tier: "medium" },
    });
    expect(start.ok()).toBeTruthy();
    const callId = (await start.json()).call_id as string;
    expect(callId).toBeTruthy();

    const end = await request.post("/api/call/end", {
      data: { callId, reason: "user_stop" },
    });
    expect(end.status()).toBe(202);

    const fin = await request.get(`/api/call/${callId}/finalization`);
    expect(fin.ok()).toBeTruthy();
    expect((await fin.json()).call_id).toBe(callId);
  });
});

test.describe("Dev Test Studio UI", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await ensureDevLogin(page);
  });

  test("agent test studio page loads without runtime error", async ({ page }) => {
    const agentId = await defaultAgentId(page.request);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto(`/dev/agents/${agentId}/test`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await expect(page.getByText("Test configuration")).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("Browser live test")).toBeVisible();
    await expect(page.getByRole("button", { name: "Start listening" })).toBeVisible();

    const mapErrors = errors.filter((e) => e.includes(".map is not a function"));
    expect(mapErrors).toEqual([]);
  });

  test("global dev test studio page loads", async ({ page }) => {
    await page.goto("/dev/test-studio", { waitUntil: "domcontentloaded", timeout: 120000 });
    await expect(page.getByRole("heading", { name: "Test Studio" })).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("button", { name: "Start listening" })).toBeVisible();
  });
});
