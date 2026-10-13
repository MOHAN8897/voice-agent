import { expect, test } from "@playwright/test";
import { DEV_USER } from "./helpers";

const adminStorageState = process.env.ADMIN_UI_STORAGE_STATE;

test.use({ storageState: adminStorageState || { cookies: [], origins: [] } });

test.beforeEach(async ({ page }) => {
  if (adminStorageState) return;
  const login = await page.request.post("/api/dev/login", { data: DEV_USER });
  expect(login.ok()).toBeTruthy();
  expect((await login.json()).ok).toBe(true);
});

test("admin workspace keeps all six operations grouped and reachable", async ({ page }) => {
  await page.route("**/api/dev/admin/analytics*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        windowDays: 30,
        since: "2026-09-14T00:00:00Z",
        totals: {
          calls: 0,
          seconds: 0,
          missedCalls: 0,
          tenants: 0,
          tenantsActive: 0,
          users: 0,
          activeNumbers: 0,
          failedPurchases: 0,
          walletBalanceCents: 0,
        },
        callsByDay: [],
        callsByStatus: {},
        callsByDirection: {},
        topUpsByDay: [],
        topTenantsByCalls: [],
      }),
    })
  );
  await page.route("**/api/dev/admin/purchases*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ purchases: [] }) })
  );

  await page.goto("/dev/admin");

  const navigation = page.getByRole("navigation", { name: "Admin sections" });
  await expect(page.getByRole("heading", { name: "SaaS overview" })).toBeVisible();
  for (const label of ["Overview", "Web & analytics", "Users", "Verification", "Tenants", "Phone numbers"]) {
    await expect(navigation.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
  for (const group of ["Workspace", "Customer operations", "Trust", "Insights"]) {
    await expect(navigation.getByText(group, { exact: true })).toBeVisible();
  }

  await expect(page.locator("table thead > tr > th").first()).toBeVisible();
  await expect(page.locator("table thead > th")).toHaveCount(0);

  const routes = [
    ["Tenants", "/dev/admin/tenants", "Tenants"],
    ["Users", "/dev/admin/users", "Users"],
    ["Phone numbers", "/dev/admin/numbers", "Phone numbers"],
    ["Verification", "/dev/admin/verification", "Identity verification"],
    ["Web & analytics", "/dev/admin/analytics", "Web & analytics"],
    ["Overview", "/dev/admin", "SaaS overview"],
  ] as const;
  for (const [label, href, heading] of routes) {
    await navigation.getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${href.replaceAll("/", "\\/")}$`));
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(navigation.getByRole("link", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
  }
});

test("support settings render nullable server values without React input warnings", async ({ page }) => {
  const inputWarnings: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /value prop on input should not be null/i.test(message.text())) {
      inputWarnings.push(message.text());
    }
  });

  await page.route("**/api/dev/admin/support/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ config: { smtpPort: null } }),
    })
  );
  await page.route("**/api/dev/admin/support/inquiries*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ inquiries: [] }) })
  );

  await page.goto("/dev/admin/support");
  await page.getByRole("button", { name: "Mail delivery" }).click();

  const smtpPort = page.getByLabel("SMTP port");
  await expect(smtpPort).toBeVisible();
  await expect(smtpPort).toHaveValue("");
  expect(inputWarnings).toHaveLength(0);
});
