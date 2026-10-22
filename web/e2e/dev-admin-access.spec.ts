import { expect, test } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test("developer admin routes do not render for a signed-out user", async ({ page }) => {
  await page.goto("/dev/admin/support");

  await expect(page).toHaveURL(/\/dev\/login(?:\?|$)/);
  await expect(page.getByText("Support & delivery", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Dev Portal" })).toBeVisible();
});
