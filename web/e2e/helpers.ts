import type { Page } from "@playwright/test";

export const E2E_USER = { username: "e2e", password: "e2e-test" };
export const DEV_USER = { username: "dev", password: "devpass" };

/** No-op when storageState from auth.setup is used. */
export async function ensureAppLogin(_page: Page) {
  /* session established in e2e/auth.setup.ts */
}

/** Refresh dev CSRF in sessionStorage after navigation (cookie session from auth.setup). */
export async function ensureDevPortalReady(page: Page) {
  await page.evaluate(async () => {
    const r = await fetch("/api/auth/dev-me", { credentials: "include", cache: "no-store" });
    if (!r.ok) return;
    const j = await r.json();
    if (j.authenticated && j.csrf_token) {
      sessionStorage.setItem("vani_dev_csrf", j.csrf_token);
    }
  });
}
