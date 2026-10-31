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
    route.fulfill({ status: 200, json: { providers: [{ id: "sarvam", label: "Sarvam", enabled: true, configured: true, models: { stt: [{ id: "saaras:v3-realtime", realtime: true }], llm: [{ id: "sarvam-30b" }], tts: [{ id: "bulbul:v3" }] } }], telephony: { providers: [] } } })
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

  await page.getByRole("combobox", { name: "STT provider", exact: true }).selectOption("sarvam");
  await page.getByRole("combobox", { name: "STT model · realtime recognition" }).selectOption("saaras:v3-realtime");
  await expect(page.getByRole("button", { name: "Load recommended mapping" })).toBeDisabled();
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

test("speech dynamics render only the knobs published by the selected speech model", async ({ page }) => {
  const evidence = { sarvamModelAccess: true, sttVerified: true, ttsCatalogVerified: true, toolsVerified: true, capacityVerified: true, mediaFormatsVerified: true, credentialRefConfigured: true };
  const speed = { key: "speed", label: "Speaking Pace", description: "Native Bulbul pace control applied to every synthesized turn.", kind: "range", min: 0.5, max: 2, step: 0.05, default: 1, native: "pace", unit: "x" };
  const configured = {
    schemaVersion: 1, enabled: false, supportedLanguages: ["te-IN"],
    stt: { provider: "sarvam", model: "saaras:v3-realtime" },
    llm: { provider: "sarvam", modelId: "verified-text-model", apiMode: "chat_completions_v1" },
    engines: [{ id: "standard-speech", label: "Standard speech", models: [{ id: "v4-model", label: "Bulbul v4 Flash", provider: "sarvam", model: "bulbul:v4-flash", apiMode: "websocket",
      voices: [{ id: "v4-voice", label: "Telugu voice", providerVoiceId: "shubh", languages: ["te-IN"] }] }] }],
    evidence,
    voiceDynamics: { speed: 1.1, temperature: 0.6 },
  };
  await page.route("**/api/auth/dev-me", (route) => route.fulfill({ json: { authenticated: true, subject: "e2e-admin", csrf_token: "test-csrf" } }));
  await page.route("**/api/dev/stack/tiers", (route) => route.fulfill({ json: { environment: "test", config_mode: "frontend", tiers: [] } }));
  await page.route("**/api/dev/stack/catalog", (route) => route.fulfill({ json: { providers: [
    { id: "sarvam", label: "Sarvam", enabled: true, configured: true, models: {
      stt: [{ id: "saaras:v3-realtime", realtime: true }],
      llm: [{ id: "verified-text-model", api_mode: "chat_completions_v1" }],
      tts: [
        { id: "bulbul:v4-flash", api_modes: ["websocket"], knobs: [
          speed,
          { key: "temperature", label: "Expressive Inflection (Temperature)", description: "Higher values increase tone variance and prosodic richness.", kind: "range", min: 0.01, max: 1, step: 0.05, default: 0.7, native: "temperature" },
        ] },
        { id: "bulbul:v2", api_modes: ["websocket"], knobs: [
          speed,
          { key: "pitch", label: "Pitch Offset", description: "Negative values deepen the voice; positive values raise it.", kind: "range", min: -0.75, max: 0.75, step: 0.01, default: 0, native: "pitch" },
          { key: "volume", label: "Volume (Loudness)", description: "Native Bulbul loudness multiplier.", kind: "range", min: 0.1, max: 3, step: 0.05, default: 1, native: "loudness", unit: "x" },
        ] },
      ],
    } },
  ], telephony: { providers: [] } } }));
  await page.route("**/api/dev/stack/voice-profiles", (route) => route.fulfill({ json: { environment: "test", profiles: [
    { tier: "low", profileRevision: 2, composedProfile: configured, readiness: { ready: true, enabled: false, blockers: [] }, retailRate: { complete: true, usdMicrosPerMin: 12000, inrPaisePerMin: 110, fxRateInr: 92.5 } },
    { tier: "medium", profileRevision: 0, composedProfile: null, readiness: { ready: false, enabled: false, blockers: [] }, retailRate: null },
    { tier: "premium", profileRevision: null, composedProfile: null, readiness: { ready: true, enabled: true, blockers: [] }, retailRate: null },
  ] } }));

  await page.goto("/dev/stack");
  await ensureDevPortalReady(page);

  await expect(page.getByRole("heading", { name: "Acoustic Calibration & Speech Dynamics" })).toBeVisible();
  await expect(page.getByText("Speaking Pace", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Expressive Inflection (Temperature)", { exact: true })).toBeVisible();
  await expect(page.getByText("Pitch Offset", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Volume (Loudness)", { exact: true })).toHaveCount(0);

  await page.getByRole("combobox", { name: "TTS model", exact: true }).selectOption("bulbul:v2");
  await expect(page.getByText("Pitch Offset", { exact: true })).toBeVisible();
  await expect(page.getByText("Volume (Loudness)", { exact: true })).toBeVisible();
  await expect(page.getByText("Expressive Inflection (Temperature)", { exact: true })).toHaveCount(0);
});

test("profile template keeps exact catalog transports and clears voices when speech models change", async ({ page }) => {
  const evidence = { sarvamModelAccess: false, sttVerified: false, ttsCatalogVerified: false, toolsVerified: false, capacityVerified: false, mediaFormatsVerified: false, credentialRefConfigured: false };
  const template = { schemaVersion: 1, enabled: false, supportedLanguages: ["te-IN"],
    stt: { provider: "sarvam", model: "saaras:v3-realtime" },
    llm: { provider: "sarvam", modelId: "verified-text-model", apiMode: "chat_completions_v1" },
    engines: [{ id: "standard-speech", label: "Standard speech", models: [{ id: "standard-model", label: "Standard model", provider: "gemini", model: "verified-gemini-tts", apiMode: "streaming_rest",
      voices: [{ id: "standard-voice", label: "Standard voice", providerVoiceId: "Kore", languages: ["te-IN"] }] }] }], evidence };
  let templateLoads = 0;
  let writes = 0;
  await page.route("**/api/auth/dev-me", (route) => route.fulfill({ json: { authenticated: true, subject: "e2e-admin", csrf_token: "test-csrf" } }));
  await page.route("**/api/dev/stack/tiers", (route) => route.fulfill({ json: { environment: "test", config_mode: "frontend", tiers: [] } }));
  await page.route("**/api/dev/stack/catalog", (route) => route.fulfill({ json: { providers: [
    { id: "sarvam", label: "Sarvam", enabled: true, configured: true, models: { stt: [{ id: "saaras:v3-realtime", realtime: true }], llm: [{ id: "verified-text-model", api_mode: "chat_completions_v1" }], tts: [{ id: "bulbul:v3" }] } },
    { id: "gemini", label: "Gemini", enabled: true, configured: true, models: { tts: [{ id: "verified-gemini-tts", api_modes: ["unary_rest", "streaming_rest"] }] } },
  ], telephony: { providers: [] } } }));
  await page.route("**/api/dev/stack/voice-profiles", (route) => route.fulfill({ json: { environment: "test", profiles: [
    { tier: "low", profileRevision: 0, composedProfile: null, readiness: { ready: false, enabled: false, blockers: [] }, retailRate: null },
    { tier: "medium", profileRevision: 0, composedProfile: null, readiness: { ready: false, enabled: false, blockers: [] }, retailRate: { complete: true, usdMicrosPerMin: 90000, inrPaisePerMin: 859 } },
    { tier: "premium", profileRevision: null, composedProfile: null, readiness: { ready: true, enabled: true, blockers: [] }, retailRate: null },
  ] } }));
  await page.route("**/api/dev/stack/voice-profiles/medium/template", (route) => { templateLoads += 1; return route.fulfill({ json: { tier: "medium", composedProfile: template } }); });
  await page.route("**/api/dev/stack/voice-profiles/medium", (route) => { writes += 1; return route.fulfill({ json: {} }); });
  await page.goto("/dev/stack");
  await ensureDevPortalReady(page);
  await page.getByRole("button", { name: "Standard (medium)" }).click();
  await expect(page.getByTestId("pstn-profile-native-amounts")).toHaveText("$0.090000/min · ₹8.59/min");
  await page.getByRole("button", { name: "Load recommended mapping" }).click();
  await expect(page.getByRole("combobox", { name: "LLM transport" })).toHaveValue("chat_completions_v1");
  await expect(page.getByRole("combobox", { name: "Speech transport" })).toHaveValue("streaming_rest");
  await expect(page.getByRole("textbox", { name: "Provider voice ID", exact: true })).toHaveValue("Kore");
  await expect(page.getByRole("heading", { name: "Readiness evidence" }).locator("..").locator('input[type="checkbox"]:checked')).toHaveCount(0);
  await page.getByRole("combobox", { name: "Speech transport" }).selectOption("unary_rest");
  await expect(page.getByRole("textbox", { name: "Provider voice ID", exact: true })).toHaveValue("Kore");
  await page.getByRole("combobox", { name: "Speech provider" }).selectOption("sarvam");
  await expect(page.getByRole("textbox", { name: "Provider voice ID", exact: true })).toHaveCount(0);
  await page.getByRole("combobox", { name: "Speech model", exact: true }).selectOption("bulbul:v3");
  await expect(page.getByRole("combobox", { name: "Speech transport" })).toHaveValue("websocket");
  await expect(page.getByRole("combobox", { name: "Speech transport" }).locator('option[value="streaming_rest"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Premium · existing Live path" }).click();
  await expect(page.getByRole("button", { name: "Load recommended mapping" })).toHaveCount(0);
  expect(templateLoads).toBe(1);
  expect(writes).toBe(0);
});
