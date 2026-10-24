import { test, expect } from "@playwright/test";
import { saasPhoneStackFromOverride, saasPhoneStackToOverride, geminiMappedVoice } from "../lib/saas-phone-stack-form";

test("new catalog voices retain their exact supplier ID through native stack form round trips", () => {
  const id = "te-in-advisor-8";
  const form = saasPhoneStackFromOverride({ pipeline: "realtime_voice", language: "te-IN", llm: { provider: "gemini", model: "gemini-3.8-live" }, realtime_voice: { voice: id } });
  expect(form.realtimeVoice).toBe(id);
  expect((saasPhoneStackToOverride(form).realtime_voice as { voice: string }).voice).toBe(id);
  expect(geminiMappedVoice(id)).toBe(id);
});
