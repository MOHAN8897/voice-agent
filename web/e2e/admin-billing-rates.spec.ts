import { expect, test } from "@playwright/test";
import { DEV_USER, ensureDevPortalReady } from "./helpers";

type BillingRateResponse = {
  currency: string;
  rates: {
    pstnUsdPerMin: number;
    webUsdPerMin: number;
    numberMonthlyUsd: number;
    fxRateInr: number;
    pstnInrPerMin: number;
    webInrPerMin: number;
    numberMonthlyInr: number;
  };
  fx: { liveRateInr?: number | null; source?: string | null; asOf?: string | null };
};

test.use({ storageState: { cookies: [], origins: [] } });

test("admin rate save keeps native INR input through reload", async ({ page }) => {
  const username = process.env.DEV_PORTAL_USERNAME || DEV_USER.username;
  const password = process.env.DEV_PORTAL_PASSWORD || DEV_USER.password;
  const login = await page.request.post("/api/dev/login", { data: { username, password } });
  expect(login.ok()).toBeTruthy();
  expect((await login.json()).ok).toBe(true);

  // Read-only baseline against the real local API. The write below is mocked
  // so this regression never changes a configured billing rate.
  const baselineResponse = await page.request.get("/api/dev/admin/billing-rates");
  expect(baselineResponse.ok()).toBeTruthy();
  const baseline: BillingRateResponse = await baselineResponse.json();
  expect(Number.isFinite(baseline.rates.pstnInrPerMin)).toBe(true);

  let savedRates: BillingRateResponse | null = null;
  let savedInrRate: number | null = null;
  await page.route("**/api/dev/admin/billing-rates", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      expect(body.rateCurrency).toBe("INR");
      expect(body.pstnInrPerMin).toBe("5.00");
      expect(body.pstnUsdPerMin).toBeUndefined();
      const rate = Number(body.pstnInrPerMin);
      const fx = Number(body.fxRateInr);
      savedInrRate = rate;
      savedRates = {
        ...baseline,
        rates: {
          ...baseline.rates,
          pstnInrPerMin: rate,
          pstnUsdPerMin: Math.round((rate / fx) * 1_000_000) / 1_000_000,
          fxRateInr: fx,
        },
      };
      await route.fulfill({ status: 200, json: { ok: true, ...savedRates } });
      return;
    }

    if (route.request().method() === "GET" && savedRates) {
      await route.fulfill({ status: 200, json: savedRates });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/dev/admin/wallets", (route) =>
    route.fulfill({ status: 200, json: { wallets: [], currency: "USD", fxRateInr: baseline.rates.fxRateInr } })
  );
  await page.route("**/api/dev/admin/purchases**", (route) =>
    route.fulfill({ status: 200, json: { purchases: [] } })
  );
  await page.route("**/api/dev/admin/payments/orders**", (route) =>
    route.fulfill({ status: 200, json: { orders: [] } })
  );
  await page.route("**/api/dev/admin/payments", (route) =>
    route.fulfill({ status: 200, json: { internationalEnabled: false, currency: "USD" } })
  );

  await page.goto("/dev/admin/billing");
  await ensureDevPortalReady(page);
  await expect(page.getByTestId("admin-wallet-currency-display")).toBeVisible();
  await page.getByTestId("admin-wallet-currency-display").selectOption("INR");
  await expect(page.getByText("Prices (INR)", { exact: true })).toBeVisible();

  const pstnRate = page.getByLabel("PSTN INR per minute");
  await expect(pstnRate).toBeVisible();
  await pstnRate.fill("5.00");
  const reload = page.waitForResponse((response) =>
    response.request().method() === "GET" &&
    new URL(response.url()).pathname.endsWith("/api/dev/admin/billing-rates")
  );
  await page.getByRole("button", { name: "Save rates" }).click();
  await reload;

  await expect(pstnRate).toHaveValue("5");
  expect(savedInrRate).toBe(5);

  const unchangedResponse = await page.request.get("/api/dev/admin/billing-rates");
  expect(unchangedResponse.ok()).toBeTruthy();
  const unchanged: BillingRateResponse = await unchangedResponse.json();
  expect(unchanged.rates.pstnInrPerMin).toBe(baseline.rates.pstnInrPerMin);
});
