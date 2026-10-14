import { expect, test } from "@playwright/test";
import {
  DEFAULT_CALL_END_FAREWELL,
  defaultCallEndPolicy,
  normalizeCallEndPolicyState,
} from "../lib/call-end-policy";

const SUPPORTED_LANGUAGES = [
  "bn-IN",
  "en-GB",
  "en-IN",
  "en-US",
  "gu-IN",
  "hi-IN",
  "kn-IN",
  "ml-IN",
  "mr-IN",
  "pa-IN",
  "ta-IN",
  "te-IN",
];

test("fine-tune hangup defaults cover every supported language", () => {
  expect(Object.keys(DEFAULT_CALL_END_FAREWELL).sort()).toEqual([...SUPPORTED_LANGUAGES].sort());

  for (const language of SUPPORTED_LANGUAGES) {
    const expected = DEFAULT_CALL_END_FAREWELL[language];
    expect(expected, `${language} needs a default farewell`).toBeTruthy();
    expect(defaultCallEndPolicy(language).farewell).toBe(expected);
    expect(normalizeCallEndPolicyState({ farewell: expected }, language).farewell).toBe(expected);
  }
});

test("changing language replaces a stock farewell with the selected locale default", () => {
  for (const language of SUPPORTED_LANGUAGES) {
    const normalized = normalizeCallEndPolicyState(
      { allowedReasons: ["goodbye"], farewell: DEFAULT_CALL_END_FAREWELL["en-IN"] },
      language,
    );
    expect(normalized.farewell).toBe(DEFAULT_CALL_END_FAREWELL[language]);
  }
});
