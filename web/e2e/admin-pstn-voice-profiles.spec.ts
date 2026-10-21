import { expect, test } from "@playwright/test";
import { ensureDevPortalReady } from "./helpers";

test("PSTN profile readiness and native rate gate activation independently", async ({ page }) => {
  let activationRequests = 0;
  let savedProfileEnabled: unknown;
  await page.route("**/api/auth/dev-me", (route) =>
    route.fulfill({ status: 200, json: { authenticated: true, subject: "e2e-admin", csrf_token: "test-csrf" } })
  );
  await page.route("**/api/dev/stack/tiers", (route) =>
    route.fulfill({ status: 200, json: { environment: "test", config_mode: "frontend", tiers: [] } })
  );
  await page.route("**/api/dev/stack/catalog", (route) =>
    route.fulfill({ status: 200, json: { providers: [], telephony: { providers: [] } } })
  );
  await page.route("**/api/dev/stack/voice-profiles", (route) =>
    route.fulfill({
      status: 200,
      json: {
        environment: "test",
        profiles: [
          {
            tier: "low",
            profileRevision: 0,
            composedProfile: null,
            readiness: {
              ready: false,
              enabled: false,
              blockers: [
                { code: "model_access", message: "Approved model account access is not verified." },
                { code: "voice_catalog", message: "No verified voice is available for the exact TTS model." },
                { code: "languages", message: "No supported language has been verified." },
                { code: "capacity", message: "Provider capacity has not been verified." },
                { code: "tools", message: "Required tool support has not been verified." },
              ],
            },
            retailRate: null,
          },
          {
            tier: "medium",
            profileRevision: 3,
            composedProfile: {
              schemaVersion: 1,
              enabled: false,
              supportedLanguages: ["te-IN"],
              stt: { provider: "approved-stt", model: "verified-stt-model" },
              llm: { provider: "approved-llm", modelId: "verified-llm-model", apiMode: "streaming" },
              engines: [],
              evidence: {
                sarvamModelAccess: true,
                sttVerified: true,
                ttsCatalogVerified: true,
                toolsVerified: true,
                capacityVerified: true,
                mediaFormatsVerified: true,
                credentialRefConfigured: true,
              },
            },
            readiness: { ready: true, enabled: false, blockers: [] },
            retailRate: null,
          },
          {
            tier: "premium",
            profileRevision: null,
            composedProfile: null,
            readiness: { ready: true, enabled: true, blockers: [] },
            retailRate: null,
            readOnly: true,
          },
        ],
      },
    })
  );
  await page.route("**/api/dev/stack/voice-profiles/*/activation", async (route) => {
    activationRequests += 1;
    await route.fulfill({ status: 409, json: { detail: "Activation is blocked in this test." } });
  });
  await page.route("**/api/dev/stack/voice-profiles/low", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as { composedProfile?: { enabled?: boolean } };
      savedProfileEnabled = body.composedProfile?.enabled;
      await route.fulfill({ status: 200, json: {} });
      return;
    }
    await route.continue();
  });

  await page.goto("/dev/stack");
  await ensureDevPortalReady(page);

  await expect(page.getByRole("heading", { name: "PSTN voice profiles" })).toBeVisible();
  await expect(page.getByTestId("pstn-profile-configured")).toContainText("Not configured");
  await expect(page.getByText("Approved model account access is not verified.", { exact: true })).toBeVisible();
  await expect(page.getByText("No verified voice is available for the exact TTS model.", { exact: true })).toBeVisible();
  await expect(page.getByText(/No native per-tier PSTN price is configured/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Enable for new PSTN calls" })).toBeDisabled();
  expect(activationRequests).toBe(0);

  await page.getByRole("textbox", { name: "STT provider ID" }).fill("reviewed-stt");
  await page.getByRole("button", { name: "Save disabled draft" }).click();
  await expect(page.getByRole("status")).toContainText("Profile draft saved. It remains disabled.");
  expect(savedProfileEnabled).toBe(false);
  expect(activationRequests).toBe(0);

  await page.getByRole("button", { name: "Standard (medium)" }).click();
  await expect(page.getByTestId("pstn-profile-configured")).toContainText("Saved · revision 3");
  await expect(page.getByTestId("pstn-profile-readiness")).toContainText("Ready");
  await expect(page.getByTestId("pstn-profile-enablement")).toContainText("Disabled");
  await expect(page.getByTestId("pstn-profile-retail-rate")).toContainText("Not configured");
  await expect(page.getByText(/No native per-tier PSTN price is configured/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Enable for new PSTN calls" })).toBeDisabled();
  expect(activationRequests).toBe(0);

  await page.getByRole("button", { name: "Premium · existing Live path" }).click();
  await expect(page.getByTestId("pstn-profile-configured")).toContainText("Existing Live path");
  await expect(page.getByText(/existing Live stack and legacy billing rate/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Enable for new PSTN calls" })).toHaveCount(0);
  expect(activationRequests).toBe(0);
});
