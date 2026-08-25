import type { Page } from "@playwright/test";

export const E2E_USER = { username: "e2e", password: "e2e-test" };

/** No-op when storageState from global-setup is used. */
export async function ensureAppLogin(_page: Page) {
  /* session established in e2e/global-setup.ts */
}
