import { expect, test, type Page } from "@playwright/test";

test.use({ storageState: process.env.BILLING_AUDIT_STORAGE_STATE || "e2e/.auth/user.json" });

function insights(empty = false) {
  return {
    asOf: new Date().toISOString(), since: "2026-10-01T00:00:00Z", callsReviewed: empty ? 0 : 12, windowCapped: false,
    notes: ["API costs use reported tokens. Carrier tariffs are estimates unless a CDR is available."], samples: [],
    channels: (["pstn", "browser"] as const).map((channel) => ({
      channel, label: channel === "pstn" ? "PSTN calls" : "Web agent test calls",
      costUsd: empty ? 0 : 1, costInr: empty ? 0 : 80, connectedMinutes: empty ? 0 : 10,
      calls: empty ? 0 : 6, tenants: empty ? 0 : 2, missingCostCalls: 0, coveragePercent: empty ? null : 100,
      averageUsdPerMin: empty ? null : channel === "pstn" ? .1 : .025,
      averageInrPerMin: empty ? null : channel === "pstn" ? 8 : 2,
      apiUsd: .2, apiInr: 16, carrierUsd: channel === "pstn" ? .8 : 0, carrierInr: channel === "pstn" ? 64 : 0,
      transcriptionUsd: 0, transcriptionInr: 0, unconnectedPrewarmUsd: 0, unconnectedPrewarmInr: 0,
      unconnectedPrewarmRecords: 0, carrierCdrCalls: channel === "pstn" ? 5 : 0,
      carrierEstimatedCalls: channel === "pstn" ? 1 : 0, reconstructedCalls: 0,
      currentPriceUsdPerMin: .2, currentPriceInrPerMin: 16, models: ["gemini-3.8-live"],
    })),
  };
}

async function mockWalletResources(page: Page) {
  await page.route("**/api/dev/admin/wallets", (route) => route.fulfill({ json: { wallets: [], currency: "USD" } }));
  await page.route("**/api/dev/admin/purchases**", (route) => route.fulfill({ json: { purchases: [] } }));
  await page.route("**/api/dev/admin/payments/orders**", (route) => route.fulfill({ json: { orders: [] } }));
  await page.route("**/api/dev/admin/payments", (route) => route.fulfill({ json: { configured: false, internationalEnabled: false, currency: "USD" } }));
  await page.route("**/api/dev/admin/billing-rates", (route) => {
    // Fail instead of modifying any real pricing during this test.
    expect(route.request().method()).toBe("GET");
    return route.fulfill({ json: { currency: "USD", rates: {
      pstnUsdPerMin: .2, webUsdPerMin: .1, numberMonthlyUsd: 4,
      pstnInrPerMin: 16, webInrPerMin: 8, numberMonthlyInr: 320, fxRateInr: 80,
    }, fx: { chargeRateInr: 80, liveRateInr: 80 } } });
  });
}

test("supplier averages calculate margin and fill a draft without saving prices", async ({ page }) => {
  await mockWalletResources(page);
  await page.route("**/api/dev/admin/billing/cost-insights?**", (route) => route.fulfill({ json: insights() }));
  await page.goto("/dev/admin/billing");
  await page.getByTestId("admin-wallet-currency-display").selectOption("USD");
  await expect(page.getByTestId("cost-channel-pstn")).toContainText("$0.1000");
  await expect(page.getByTestId("suggested-price-browser")).toContainText("0.035715");
  await page.getByLabel("Target gross margin percent").fill("50");
  await expect(page.getByTestId("suggested-price-browser")).toContainText("0.0500");
  await page.getByTestId("use-suggested-browser").click();
  await expect(page.getByTestId("admin-rate-web-usd")).toHaveValue("0.050000");
  await page.getByLabel("Target gross margin percent").fill("100");
  await expect(page.getByRole("alert").filter({ hasText: "Enter a margin" })).toBeVisible();
  await expect(page.getByTestId("use-suggested-pstn")).toBeDisabled();
  await page.getByLabel("Target gross margin percent").fill("30");
  await page.getByTestId("admin-wallet-currency-display").selectOption("INR");
  await expect(page.getByTestId("suggested-price-browser")).toContainText("2.86");
  const sampleHeader = page.getByTestId("admin-cost-insights").getByRole("columnheader", { name: "Call / tenant" });
  await expect(sampleHeader).not.toBeVisible();
  await page.getByText("Random call audit sample (0)", { exact: true }).click();
  await expect(sampleHeader).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const panel = page.getByTestId("admin-cost-insights");
  expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

test("cost report refreshes every minute and sends the selected date window", async ({ page }) => {
  await page.clock.install();
  await mockWalletResources(page);
  let requests = 0;
  let window = "";
  await page.route("**/api/dev/admin/billing/cost-insights?**", (route) => {
    requests++;
    window = new URL(route.request().url()).searchParams.get("days") || "";
    return route.fulfill({ json: insights() });
  });
  await page.goto("/dev/admin/billing");
  await expect(page.getByTestId("cost-channel-browser")).toBeVisible();
  const initial = requests;
  await page.clock.fastForward(61_000);
  await expect.poll(() => requests).toBeGreaterThan(initial);
  await page.getByLabel("Cost analysis window").selectOption("7");
  await expect.poll(() => window).toBe("7");
});

test("empty and failed reports show no invented average and recover on refresh", async ({ page }) => {
  await mockWalletResources(page);
  let failed = false;
  await page.route("**/api/dev/admin/billing/cost-insights?**", (route) => failed
    ? route.fulfill({ status: 503, json: { detail: "Usage store unavailable" } })
    : route.fulfill({ json: insights(true) }));
  await page.goto("/dev/admin/billing");
  await expect(page.getByTestId("cost-channel-pstn")).toContainText("No usable cost data yet");
  await expect(page.getByTestId("use-suggested-pstn")).toBeDisabled();
  failed = true;
  await page.getByTestId("cost-insights-refresh").click();
  await expect(page.getByText("Usage store unavailable")).toBeVisible();
  failed = false;
  await page.getByTestId("cost-insights-refresh").click();
  await expect(page.getByTestId("cost-channel-browser")).toContainText("No usable cost data yet");
});

test("a delayed old window cannot replace the selected window's costs", async ({ page }) => {
  await mockWalletResources(page);
  const pending: (() => void)[] = [];
  await page.route("**/api/dev/admin/billing/cost-insights?**", async (route) => {
    const days = new URL(route.request().url()).searchParams.get("days");
    if (days === "30") await new Promise<void>((resolve) => pending.push(resolve));
    const report = insights();
    if (days === "7") report.channels[1].averageUsdPerMin = .03;
    await route.fulfill({ json: report });
  });
  await page.goto("/dev/admin/billing");
  await expect.poll(() => pending.length).toBeGreaterThan(0);
  await page.getByTestId("admin-wallet-currency-display").selectOption("USD");
  await page.getByLabel("Cost analysis window").selectOption("7");
  await expect(page.getByTestId("cost-channel-browser")).toContainText("$0.0300");
  const oldResponse = page.waitForResponse((response) => response.url().includes("cost-insights?days=30"));
  pending.forEach((resolve) => resolve());
  await oldResponse;
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("cost-channel-browser")).toContainText("$0.0300");
});
