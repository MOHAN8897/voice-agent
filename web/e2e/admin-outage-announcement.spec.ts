import { expect, test } from "@playwright/test";
import { ensureDevPortalReady } from "./helpers";

const PAYLOAD = {
  agentId: "agent-outage-1",
  tenantId: "tenant-outage-1",
  name: "Outage Agent",
  spokenLanguages: ["te-IN"],
  languages: ["te-IN", "en-IN"],
  promiseCallback: true,
  transcript: "",
  variants: [
    { id: "callback_promise", label: "Callback promise" },
    { id: "call_back", label: "Safe call-back" },
    { id: "disclosure", label: "Recording disclosure" },
  ],
  defaults: {
    "te-IN": { callback_promise: "మేము తిరిగి కాల్ చేస్తాము.", call_back: "దయచేసి తిరిగి కాల్ చేయండి.", disclosure: "ఈ కాల్ రికార్డ్ చేయబడుతుంది." },
    "en-IN": { callback_promise: "We will call you back.", call_back: "Please call us back.", disclosure: "This call is recorded." },
  },
  clips: [],
};

test("platform admins configure the outage announcement on its own page", async ({ page }) => {
  let saved: unknown;
  await page.route("**/api/auth/dev-me", (route) =>
    route.fulfill({ json: { authenticated: true, subject: "e2e-admin", csrf_token: "test-csrf" } })
  );
  await page.route("**/api/dev/admin/agents/agent-outage-1/technical-fallback", async (route) => {
    if (route.request().method() === "PATCH") {
      saved = route.request().postDataJSON();
      await route.fulfill({ json: { ok: true } });
      return;
    }
    await route.fulfill({ json: PAYLOAD });
  });

  await page.goto("/dev/agents/agent-outage-1/fallback");
  await ensureDevPortalReady(page);

  await expect(page.getByText("TTS outage announcement", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Agent: Outage Agent · Telugu", { exact: true })).toBeVisible();
  await expect(page.getByText("Tenant tenant-outage-1 · Agent agent-outage-1", { exact: true })).toBeVisible();

  const callbackSwitch = page.getByRole("switch", { name: "Promise the caller a callback" });
  await expect(callbackSwitch).toHaveAttribute("aria-checked", "true");

  await page.getByLabel("Internal transcript note").fill("Outage message for operator review");
  await expect(page.getByText("This note is never synthesized during an outage. Callers hear a recording only.", { exact: true })).toBeVisible();
  await expect(page.getByText("All 3 messages use the platform recordings.", { exact: true })).toBeVisible();

  await callbackSwitch.click();
  await expect(callbackSwitch).toHaveAttribute("aria-checked", "false");
  await page.getByRole("button", { name: "Save announcement settings" }).click();

  await expect.poll(() => saved).toEqual({ promiseCallback: false, transcript: "Outage message for operator review" });
  await expect(page.getByRole("status")).toContainText("Outage announcement settings saved.");
});
