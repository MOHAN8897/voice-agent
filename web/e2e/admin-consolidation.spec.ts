import { expect, test } from "@playwright/test";

const evidence = { sarvamModelAccess: true, sttVerified: true, ttsCatalogVerified: true,
  toolsVerified: true, capacityVerified: true, mediaFormatsVerified: true, credentialRefConfigured: true };
const profile = {
  schemaVersion: 1, enabled: true, label: "Economical", supportedLanguages: ["te-IN"],
  stt: { provider: "sarvam", model: "saaras:v3-realtime" },
  llm: { provider: "sarvam", modelId: "sarvam-105b-conversations", apiMode: "chat_completions_v1" },
  engines: [{ id: "speech", label: "Speech", models: [{ id: "model", label: "Model", provider: "gnani",
    model: "timbre-v3.0", apiMode: "websocket", voices: [{ id: "voice", label: "Voice", providerVoiceId: "Shivani", languages: ["te-IN"] }] }] }],
  evidence: Object.fromEntries(Object.keys(evidence).map(key => [key, false])),
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/dev/admin/**", route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = { items: [] };
    if (path.endsWith("/analytics")) data = { windowDays: 30, since: "2026-10-01T00:00:00Z",
      totals: { calls: 12, seconds: 720, missedCalls: 1, tenants: 3, tenantsActive: 2, users: 4,
        activeNumbers: 2, failedPurchases: 0, walletBalanceCents: 1234, walletBalanceInrPaise: 567800 },
      callsByDay: [{ date: "2026-10-24", calls: 0, seconds: 0 }, { date: "2026-10-25", calls: 2, seconds: 120 }, { date: "2026-10-26", calls: 10, seconds: 600 }],
      callsByStatus: { completed: 12 }, callsByDirection: { outbound: 12 }, callsByChannel: { pstn: { calls: 12, seconds: 720 } },
      topUpsByDay: [{ date: "2026-10-26", cents: 1000, inrPaise: 50000 }], topTenantsByCalls: [{ name: "Test workspace", calls: 12 }] };
    else if (path.endsWith("/purchases")) data = { purchases: [] };
    else if (path.endsWith("/tenants")) data = { tenants: [{ tenantId: "synthetic-tenant", name: "Test workspace", status: "active", plan: "starter" }], total: 1 };
    else if (path.endsWith("/users")) data = { users: [], total: 0 };
    else if (path.endsWith("/billing-rates")) data = { rates: { webInrPerMin: 2, numberMonthlyInr: 300, fxRateInr: 95 } };
    return route.fulfill({ json: data });
  });
});

test("overview is the first page with real currency totals and visible chart bars", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/dev");
  await expect(page.getByRole("heading", { name: "SaaS overview" })).toBeVisible();
  const sidebar = page.locator("aside").first();
  await expect(sidebar.locator("ul a").first()).toHaveText("Overview");
  await expect(sidebar.getByRole("link", { name: "Agents & brain" })).toHaveCount(0);
  await expect(sidebar.getByRole("link", { name: "SaaS phone AI" })).toHaveCount(0);
  await expect(sidebar.getByRole("link", { name: "Tenants & users", exact: true })).toHaveCount(1);
  await expect(page.getByText("₹5,678.00", { exact: true })).toBeVisible();
  const chart = page.getByRole("img", { name: "Calls per day" });
  expect((await chart.locator("div[style]").last().boundingBox())!.height).toBeGreaterThan(100);
  await expect(chart.locator("div[style]").last()).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  expect((await chart.locator("div[style]").first().boundingBox())!.height).toBe(0);
  for (const name of ["Calls by status", "Busiest tenants"]) {
    const card = page.locator("article").filter({ has: page.getByRole("heading", { name, exact: true }) });
    expect(await card.locator("table").evaluate(table => table.parentElement!.scrollWidth <= table.parentElement!.clientWidth)).toBe(true);
  }
  await page.getByRole("button", { name: "7d", exact: true }).click();
  await expect(page.getByText("Calls (7d)", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../artifacts/call-quality-review/admin-readiness-console-20261027/overview.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("retired admin pages redirect and users keep their workspace filter", async ({ page }) => {
  await page.goto("/dev/admin/users?tenantId=synthetic-tenant");
  await expect(page).toHaveURL(/\/dev\/admin\/tenants\?.*section=users/);
  await expect(page.getByRole("heading", { name: "Users & Memberships", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "Tenants & users" })).toHaveAttribute("aria-current", "page");
  const customerNav = page.getByRole("navigation", { name: "Customer sections" });
  await expect(customerNav.getByRole("link", { name: "Users & memberships" })).toHaveAttribute("href", /tenantId=synthetic-tenant/);
  await customerNav.getByRole("link", { name: "Workspaces", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tenants", exact: true })).toBeVisible();
  for (const path of ["/dev/agents", "/dev/agents/old-agent/brain", "/dev/admin"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/dev$/);
  }
});

test("a slow analytics response cannot overwrite the newest time window", async ({ page }) => {
  let slowResponseFinished = false;
  await page.route("**/api/dev/admin/analytics?*", async route => {
    const days = Number(new URL(route.request().url()).searchParams.get("days") || 30);
    if (days === 7) await new Promise(resolve => setTimeout(resolve, 400));
    await route.fulfill({ json: { windowDays: days, since: "2026-10-01T00:00:00Z",
      totals: { calls: days, seconds: days, missedCalls: 0, tenants: 0, tenantsActive: 0, users: 0,
        activeNumbers: 0, failedPurchases: 0, walletBalanceCents: 0, walletBalanceInrPaise: 0 },
      callsByDay: [], callsByStatus: {}, callsByDirection: {}, callsByChannel: {}, topUpsByDay: [], topTenantsByCalls: [] } });
    if (days === 7) slowResponseFinished = true;
  });
  await page.goto("/dev");
  await page.getByRole("button", { name: "7d", exact: true }).click();
  await page.getByRole("button", { name: "90d", exact: true }).click();
  await expect.poll(() => slowResponseFinished).toBe(true);
  const card = page.locator("article").filter({ has: page.getByText("Calls (90d)", { exact: true }) });
  await expect(card.locator("p").nth(1)).toHaveText("90");
});

test("stack verification has a usable action and pricing has no duplicate phone rates", async ({ page }) => {
  let verified = false;
  const row = () => ({ tier: "low", label: "Economical", profileRevision: verified ? 2 : 1,
    composedProfile: { ...profile, evidence: verified ? evidence : profile.evidence },
    readiness: { ready: verified, enabled: true, blockers: verified ? [] : [{ code: "stt_unverified", message: "Streaming recognition has not been verified." }] },
    retailRate: { complete: true, inrPaisePerMin: 100, usdMicrosPerMin: 10000, fxRateInr: 100, version: 1 } });
  await page.route("**/api/dev/stack/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/voice-profiles/low/verify")) {
      expect(route.request().postDataJSON()).toEqual({ expectedRevision: 1 }); verified = true;
      return route.fulfill({ json: { profile: row(), checks: Object.fromEntries(Object.keys(evidence).map(key => [key, { passed: true, detail: `${key} verified` }])) } });
    }
    if (path.endsWith("/voice-profiles")) return route.fulfill({ json: { environment: "test", profiles: [row()] } });
    if (path.endsWith("/catalog")) return route.fulfill({ json: { providers: [
      { id: "sarvam", enabled: true, configured: true, models: { stt: [{ id: "saaras:v3-realtime" }], llm: [{ id: "sarvam-105b-conversations" }] } },
      { id: "gnani", enabled: true, configured: true, models: { tts: [{ id: "timbre-v3.0", api_mode: "websocket", voices: profile.engines[0].models[0].voices }] } },
    ] } });
    return route.fulfill({ json: { ok: true } });
  });
  await page.goto("/dev/saas-phone-stack");
  await expect(page).toHaveURL(/\/dev\/stack$/);
  await expect(page.getByText("Enabled · verification needed", { exact: true })).toBeVisible();
  await page.getByTestId("verify-profile-readiness").click();
  await expect(page.getByRole("list", { name: "Verification results" })).toContainText("sttVerified verified");
  await expect(page.getByText(/Readiness Blockers/)).toHaveCount(0);
  await page.getByRole("tab", { name: "Pricing", exact: true }).click();
  await expect(page.getByText("Default Web Calling Rate", { exact: true })).toBeVisible();
  await expect(page.getByText(/Economical Tier \(Low\) Rate|Standard Regional Tier \(Medium\) Rate|Gemini 3.8 Live \(Premium\) Rate/)).toHaveCount(0);
  const savedPrices = page.waitForRequest(request => request.url().includes('/api/dev/admin/billing-rates') && request.method() === 'PUT');
  await page.getByRole('button', { name: 'Save Platform Prices', exact: true }).click();
  const payload = (await savedPrices).postDataJSON();
  expect(Object.keys(payload).filter(key => /^pstn/i.test(key))).toEqual([]);
  expect(payload).toHaveProperty('webInrPerMin');
  expect(payload).toHaveProperty('didMonthlyInr');
});
