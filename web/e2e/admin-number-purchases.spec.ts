import { expect, test, type Page } from "@playwright/test";

// The admin "Number purchases" page against the shapes
// server/services/saas/number_purchase_admin.py returns. Synthetic data only.

const BASE = process.env.WEB_URL || "http://127.0.0.1:3391";

const health = {
  provider: "vobiz",
  configured: true,
  rent: { inr: 564, usd: 6 },
  carrierBalance: { ok: true, balance: 481.78, currency: "INR" },
  inventoryPricing: { ok: true, inventoryCount: 200, pricedCount: 200, aboveRentCount: 200, cheapestInr: 600, highestInr: 1100 },
  alerts: [
    {
      code: "carrier_price_above_retail", scope: "platform", severity: "error",
      title: "Tenants cannot buy any number: rent is below every Vobiz price",
      detail: "Phone number rent is ₹564.00/month but the cheapest Vobiz number costs ₹600.00 (setup + first month). All 200 inventory numbers are hidden from tenants.",
      action: "Raise “Phone number monthly rent” to at least ₹600.00 in Wallet & rates.",
      href: "/dev/admin/billing",
      affected: { count: 3, tenants: ["Acme Realty"], numbers: ["+918041230002"], lastAt: "2026-10-30T08:00:00Z" },
    },
    {
      code: "carrier_balance_exhausted", scope: "platform", severity: "error",
      title: "Vobiz account balance is too low to buy numbers",
      detail: "The Vobiz balance is ₹481.78, below the cheapest number (₹600.00 setup + first month). Purchases are refused before tenants are charged.",
      action: "Top up the Vobiz account by at least ₹118.22 (more to buy several numbers).",
      href: null,
    },
    {
      code: "purchases_need_attention", scope: "number", severity: "error",
      title: "1 purchase needs attention", detail: "Tenants were charged and the number is not active yet; 1 refund(s) failed.",
      action: "Open each one below: retry provisioning or refund.", href: null, filter: "needs_attention",
    },
  ],
  counts: { succeeded: 4, provisioning: 0, needs_attention: 1, failed: 0, refunded: 1 },
  refusalsLast7Days: 3,
  checkedAt: "2026-10-30T09:00:00Z",
};

const stuck = {
  purchaseId: "11111111-1111-4111-8111-111111111111", tenantId: "t-1", tenantName: "Acme Realty", e164: "+918041230002",
  provider: "vobiz", status: "needs_attention", rawStatus: "failed", stuck: false,
  createdAt: "2026-10-30T07:00:00Z", updatedAt: "2026-10-30T07:01:00Z",
  charged: { usd: 6, inr: 564, at: "2026-10-30T07:00:00Z" }, refund: { state: "failed" },
  job: { status: "failed", attempts: 1, updatedAt: "2026-10-30T07:01:00Z" },
  issue: { code: "refund_failed", scope: "number", severity: "error", title: "Refund could not be credited",
    detail: "Provisioning failed but the wallet refund did not go through.", action: "Use “Refund” here (it is idempotent) or credit the wallet manually.", href: null },
  carrier: { errorType: "VobizApiError", providerStatus: 500, context: { carrierBalance: 481.78, carrierRequired: 600, currency: "INR" } },
  canRetry: false, canRefund: true,
};
const refunded = {
  ...stuck, purchaseId: "22222222-2222-4222-8222-222222222222", status: "refunded", tenantName: "Beta Clinics",
  refund: { state: "refunded", amount: { usd: 6, inr: 564, at: "2026-10-30T06:02:00Z" } },
  issue: { code: "carrier_balance_exhausted", scope: "platform", severity: "error", title: "Vobiz account balance is too low to buy numbers",
    detail: "x", action: "Top up the Vobiz parent account, then ask affected tenants to try again.", href: null },
  canRefund: false,
};

async function boot(page: Page) {
  const calls: Array<{ url: string; method: string; body: unknown }> = [];
  await page.context().addCookies([{ name: "vani_dev_session", value: "synthetic", url: BASE }]);
  await page.route("**/api/**", (route) => route.fulfill({ json: {} }));
  await page.route("**/api/auth/dev-me", (route) =>
    route.fulfill({ json: { authenticated: true, subject: "ops@example.invalid", csrf_token: "csrf" } })
  );
  await page.route("**/api/dev/admin/number-purchases**", (route) => {
    const req = route.request();
    const url = new URL(req.url());
    calls.push({ url: url.pathname + url.search, method: req.method(), body: req.postDataJSON?.() ?? null });
    if (url.pathname.endsWith("/health")) return route.fulfill({ json: health });
    if (url.pathname.endsWith("/refusals")) {
      return route.fulfill({ json: { windowDays: 7, total: 1, items: [{
        id: "r1", at: "2026-10-30T08:00:00Z", tenantId: "t-1", tenantName: "Acme Realty", e164: "+918041230002",
        code: "carrier_price_above_retail", platform: true, httpStatus: 409,
        context: { carrierPrice: 600, retailPrice: 564, currency: "INR" },
        issue: { code: "carrier_price_above_retail", scope: "platform", severity: "warning",
          title: "Number rent is below Vobiz's price for this number", detail: "x",
          action: "Raise “Phone number monthly rent” in Wallet & rates to at least the Vobiz price shown.", href: "/dev/admin/billing" },
      }] } });
    }
    if (url.pathname.endsWith("/refund") && req.method() === "POST") return route.fulfill({ json: { ok: true, refunded: true } });
    if (url.pathname.endsWith(stuck.purchaseId)) {
      return route.fulfill({ json: { ...stuck, timeline: [
        { at: "2026-10-30T07:00:00Z", kind: "created", label: "Purchase created", tone: "info" },
        { at: "2026-10-30T07:00:01Z", kind: "debit", label: "Wallet debited ₹564.00 / $6.00", tone: "info" },
        { at: "2026-10-30T07:01:00Z", kind: "number.provision.failed", label: "Provisioning failed", detail: "Vobiz account balance is too low to buy numbers", tone: "error" },
      ] } });
    }
    const status = url.searchParams.get("status");
    const items = [stuck, refunded].filter((p) => !status || p.status === status);
    return route.fulfill({ json: { items, total: items.length, limit: 200, offset: 0, counts: health.counts } });
  });
  return calls;
}

test("platform blockers come first with the fix", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await boot(page);
  await page.goto("/dev/admin/purchases");
  await expect(page.getByRole("heading", { name: "Number purchases" })).toBeVisible();
  await expect(page.getByTestId("tile-carrier-balance")).toContainText("₹481.78");
  const rent = page.getByTestId("alert-carrier_price_above_retail");
  await expect(rent).toContainText("rent is below every Vobiz price");
  await expect(rent).toContainText("Acme Realty");
  await expect(rent.getByRole("link", { name: "Fix it" })).toHaveAttribute("href", "/dev/admin/billing");
  await expect(page.getByTestId("alert-carrier_balance_exhausted")).toContainText("Top up the Vobiz account");
  await expect(page.locator("aside").getByRole("link", { name: "Number purchases" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("filters, detail drawer and a guarded refund", async ({ page }) => {
  const calls = await boot(page);
  await page.goto("/dev/admin/purchases");
  await page.getByTestId("alert-purchases_need_attention").getByRole("button", { name: "Show them" }).click();
  await expect(page).toHaveURL(/status=needs_attention/);
  await expect(page.getByTestId("purchase-row")).toHaveCount(1);
  await expect(page.getByTestId("purchase-row")).toContainText("Refund could not be credited");
  await expect(page.getByTestId("purchase-row")).toContainText("Refund failed");

  await page.getByTestId("purchase-row").click();
  const drawer = page.getByTestId("accounts-drawer");
  await expect(drawer.getByTestId("purchase-issue")).toContainText("Refund could not be credited");
  await expect(drawer).toContainText("Vobiz balance ₹481.78 · needed ₹600.00");
  await expect(drawer.getByTestId("purchase-timeline")).toContainText("Provisioning failed");
  await expect(drawer.getByTestId("purchase-retry")).toHaveCount(0);

  await drawer.getByTestId("purchase-refund").click();
  await expect(page.getByTestId("action-submit")).toBeDisabled();
  await page.getByTestId("action-reason").fill("Refund after failed provisioning");
  await page.getByTestId("action-submit").click();
  await expect.poll(() => calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "Refund after failed provisioning" });
  expect(calls.find((c) => c.method === "POST")?.url).toContain(`/${stuck.purchaseId}/refund`);
});

test("refused before charge shows the real reason and figures", async ({ page }) => {
  await boot(page);
  await page.goto("/dev/admin/purchases?status=refused");
  const row = page.getByTestId("refusal-row");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("Platform");
  await expect(row).toContainText("Number rent is below Vobiz's price");
  await expect(row).toContainText("Vobiz price ₹600.00 · rent ₹564.00");
});

test("page works on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await boot(page);
  await page.goto("/dev/admin/purchases");
  await expect(page.getByTestId("purchases-health")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
