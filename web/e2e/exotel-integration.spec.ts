/**
 * Exotel integration E2E — API handshake, webhooks, Test Studio PSTN panel.
 * Run: PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:e2e -- e2e/exotel-integration.spec.ts
 */
import { test, expect } from "@playwright/test";
import { DEV_USER, ensureDevPortalReady } from "./helpers";

async function devLogin(request: import("@playwright/test").APIRequestContext) {
  const login = await request.post("/api/dev/login", { data: DEV_USER });
  expect(login.ok()).toBeTruthy();
  const body = await login.json();
  expect(body.ok, JSON.stringify(body)).toBe(true);
  return body;
}

async function defaultAgentId(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const r = await request.get("/api/agents");
  expect(r.ok()).toBeTruthy();
  const id = (await r.json()).agents?.[0]?.agent_id as string | undefined;
  if (!id) throw new Error("No agents available");
  return id;
}

test.describe.configure({ mode: "serial" });

test.describe("Exotel API", () => {
  test("public status exposes handshake fields", async ({ request }) => {
    const r = await request.get("/api/exotel/status");
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    expect(body).toHaveProperty("enabled");
    expect(body).toHaveProperty("configured");
    expect(body).toHaveProperty("handshake_ok");
    expect(body).toHaveProperty("passthru_url");
    expect(body).toHaveProperty("status_callback_url");
    if (body.configured && body.handshake_ok) {
      expect(body.account_sid).toBeTruthy();
      expect(body.balance).toBeTruthy();
    }
  });

  test("passthru webhook returns 200", async ({ request }) => {
    const sid = `e2e-passthru-${Date.now()}`;
    const r = await request.post("/api/exotel/passthru", {
      params: { CallSid: sid, From: "+911234567890", To: "+919876543210" },
    });
    expect(r.status()).toBe(200);
  });

  test("status-callback webhook returns OK", async ({ request }) => {
    const sid = `e2e-cb-${Date.now()}`;
    const r = await request.post("/api/exotel/status-callback", {
      form: { CallSid: sid, Status: "completed", From: "+911111111111", To: "+922222222222" },
    });
    expect(r.status()).toBe(200);
    expect((await r.text()).toUpperCase()).toContain("OK");
  });
});

const API_BASE = process.env.API_URL || "http://localhost:8000";
const WEB_BASE = process.env.WEB_URL || "http://localhost:3000";

test.describe("Exotel Dev API", () => {
  let devRequest: import("@playwright/test").APIRequestContext;

  test.beforeAll(async ({ playwright }) => {
    devRequest = await playwright.request.newContext({ baseURL: API_BASE });
    await devLogin(devRequest);
  });

  test.afterAll(async () => {
    await devRequest.dispose();
  });

  test("passthru registers call in dev registry", async () => {
    const sid = `e2e-passthru-${Date.now()}`;
    const passthru = await devRequest.post("/api/exotel/passthru", {
      params: { CallSid: sid, From: "+911234567890", To: "+919876543210" },
    });
    expect(passthru.status()).toBe(200);

    const calls = await devRequest.get("/api/dev/exotel/calls");
    expect(calls.status(), await calls.text()).toBe(200);
    const list = (await calls.json()).calls as Array<{ call_sid: string }>;
    expect(list.some((c) => c.call_sid === sid)).toBeTruthy();
  });

  test("numbers list returns array", async () => {
    const r = await devRequest.get("/api/dev/exotel/numbers");
    expect(r.status(), await r.text()).toBe(200);
    const j = await r.json();
    expect(Array.isArray(j.numbers)).toBeTruthy();
  });
});

test.describe("Exotel Test Studio UI", () => {
  test("PSTN panel shows handshake, balance, and outbound form", async ({ page }) => {
    const agentId = await defaultAgentId(page.request);
    await page.goto(`/dev/test-studio?agent=${agentId}`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await ensureDevPortalReady(page);
    await expect(page.getByTestId("test-studio-mode-picker")).toBeVisible({ timeout: 30000 });
    await page.waitForResponse(
      (r) => r.url().includes("/api/test-studio/prefs") && r.request().method() === "GET",
      { timeout: 15000 }
    ).catch(() => {});

    const statusWait = page.waitForResponse(
      (r) => r.url().includes("/api/dev/exotel/status") && r.status() === 200,
      { timeout: 30000 }
    );
    await page.getByTestId("test-mode-pstn").click();
    const statusRes = await statusWait;
    const st = await statusRes.json();
    expect(st.handshake_ok, st.handshake_error || JSON.stringify(st)).toBe(true);

    await expect(page.getByRole("heading", { name: "PSTN · Exotel" })).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("heading", { name: "Outbound test call" })).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("To (customer)")).toBeVisible();
    await expect(page.getByText("CallerId (ExoPhone)")).toBeVisible();
    await expect(page.getByRole("button", { name: /Place Voice AI call|Place bridge call/i })).toBeVisible();
  });
});
