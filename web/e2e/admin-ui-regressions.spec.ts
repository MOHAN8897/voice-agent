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

test("admin workspace keeps its operations grouped and reachable", async ({ page }) => {
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
  for (const label of ["Overview", "Web & analytics", "Verification", "Accounts"]) {
    await expect(navigation.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
  for (const group of ["Workspace", "Customer operations", "Trust", "Insights"]) {
    await expect(navigation.getByText(group, { exact: true })).toBeVisible();
  }

  await expect(page.locator("table thead > tr > th").first()).toBeVisible();
  await expect(page.locator("table thead > th")).toHaveCount(0);

  const routes = [
    ["Verification", "/dev/admin/verification", "Identity verification"],
    ["Web & analytics", "/dev/admin/analytics", "Web & analytics"],
    ["Overview", "/dev/admin", "SaaS overview"],
  ] as const;
  // Workspaces, users and numbers share one page; the old routes redirect there.
  await navigation.getByRole("link", { name: "Accounts", exact: true }).click();
  await expect(page).toHaveURL(/\/dev\/admin\/accounts$/);
  await expect(page.getByRole("heading", { name: "Accounts", exact: true })).toBeVisible();
  await page.goBack();
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

test("support tickets retain priority, category, and paging controls", async ({ page }) => {
  await page.route("**/api/dev/admin/support/config", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ config: {} }) })
  );
  await page.route("**/api/dev/admin/support/inquiries**", async (route) => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset") || 0);
    const count = offset === 0 ? 51 : 1;
    const inquiries = Array.from({ length: count }, (_, index) => ({
      id: `ticket-${offset + index}`,
      ticketNumber: `T-${offset + index}`,
      fullName: "Test Customer",
      email: "customer@example.test",
      category: "billing_pricing",
      priority: "high",
      subject: "Test inquiry",
      message: "Test message",
      status: "new",
      createdAt: "2026-10-14T00:00:00Z",
    }));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ inquiries }) });
  });

  await page.goto("/dev/admin/support");
  await expect(page.getByRole("heading", { name: "Support desk & delivery" })).toBeVisible();
  await expect(page.getByLabel("Filter by priority")).toBeVisible();
  await expect(page.getByLabel("Filter by category")).toBeVisible();
  await expect(page.getByLabel("Filter support tickets").locator('option[value="triaged"]')).toHaveCount(1);
  await page.getByLabel("Search support tickets").fill("invoice");

  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/dev/admin/support/inquiries") &&
      url.searchParams.get("priority") === "high" &&
      url.searchParams.get("category") === "billing_pricing" &&
      url.searchParams.get("search") === "invoice" &&
      url.searchParams.get("limit") === "51" &&
      url.searchParams.get("offset") === "0";
  });
  await page.getByLabel("Filter by priority").selectOption("high");
  await page.getByLabel("Filter by category").selectOption("billing_pricing");
  await filteredResponse;

  await expect(page.locator("tbody tr")).toHaveCount(50);
  await page.getByRole("button", { name: "Open ticket T-0" }).click();
  await expect(page.getByText("billing pricing", { exact: true })).toBeVisible();
  await expect(page.getByText("high", { exact: true })).toBeVisible();
  await expect(page.getByText("Page 1 of support tickets")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page" })).toBeEnabled();
  const nextResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/dev/admin/support/inquiries") && url.searchParams.get("offset") === "50";
  });
  await page.getByRole("button", { name: "Next page" }).click();
  await nextResponse;
  await expect(page.getByText("Page 2 of support tickets")).toBeVisible();

  const resetResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/dev/admin/support/inquiries") &&
      url.searchParams.get("status") === "all" &&
      url.searchParams.get("offset") === "0";
  });
  await page.getByLabel("Filter support tickets").selectOption("all");
  await resetResponse;
  await expect(page.getByText("Page 1 of support tickets")).toBeVisible();
});
