/** Conservative leftover-digit expander + phone strip. Mirror of server/services/spoken_numbers.py. */

const ONES = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function under100(n: number): string {
  if (n < 20) return ONES[n];
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return ones === 0 ? TENS[tens] : `${TENS[tens]} ${ONES[ones]}`;
}

export function cardinalWords(n: number): string {
  if (n < 0) return `minus ${cardinalWords(-n)}`;
  if (n < 100) return under100(n);
  if (n < 1000) {
    const rest = n % 100;
    const head = `${ONES[Math.floor(n / 100)]} hundred`;
    return rest === 0 ? head : `${head} ${under100(rest)}`;
  }
  if (n < 100_000) {
    const rest = n % 1000;
    const head = `${cardinalWords(Math.floor(n / 1000))} thousand`;
    return rest === 0 ? head : `${head} ${cardinalWords(rest)}`;
  }
  if (n < 10_000_000) {
    const rest = n % 100_000;
    const head = `${cardinalWords(Math.floor(n / 100_000))} lakh`;
    return rest === 0 ? head : `${head} ${cardinalWords(rest)}`;
  }
  const rest = n % 10_000_000;
  const head = `${cardinalWords(Math.floor(n / 10_000_000))} crore`;
  return rest === 0 ? head : `${head} ${cardinalWords(rest)}`;
}

function decimalWords(raw: string): string {
  const cleaned = raw.replace(/,/g, "");
  if (cleaned.includes(".")) {
    const [wholeS, fracS = ""] = cleaned.split(".");
    const whole = Number.parseInt(wholeS || "0", 10) || 0;
    const frac = fracS.slice(0, 2);
    if (!frac || Number.parseInt(frac, 10) === 0) return cardinalWords(whole);
    return `${cardinalWords(whole)} point ${[...frac].map((d) => ONES[Number(d)]).join(" ")}`;
  }
  return cardinalWords(Number.parseInt(cleaned || "0", 10) || 0);
}

function yearWords(year: number): string {
  if (year >= 2000 && year <= 2099) {
    const rest = year - 2000;
    if (rest === 0) return "two thousand";
    if (rest < 10) return `two thousand ${ONES[rest]}`;
    return `twenty ${under100(rest)}`;
  }
  if (year >= 1900 && year <= 1999) {
    const rest = year - 1900;
    if (rest === 0) return "nineteen hundred";
    if (rest < 10) return `nineteen oh ${ONES[rest]}`;
    return `nineteen ${under100(rest)}`;
  }
  return cardinalWords(year);
}

function clockWords(hour: number, minute: number, ampm: string): string {
  let label = ampm;
  let hour12 = hour % 12 || 12;
  if (!label) {
    label = hour < 12 ? "AM" : "PM";
    hour12 = hour % 12 || 12;
  } else {
    label = label.toUpperCase();
  }
  if (minute === 0) return `${cardinalWords(hour12)} ${label}`;
  return `${cardinalWords(hour12)} ${cardinalWords(minute)} ${label}`;
}

export function stripSpokenPhoneNumbers(text: string): string {
  if (!text) return text;
  let out = text.replace(
    /\b(?:call|phone|mobile|whatsapp|reach)(?:\s+us)?\s+at\s+[\d\s\-+().]{8,}/gi,
    ""
  );
  out = out.replace(/(?<!\d)(?:\+91[-\s]?)?\d{10}(?!\d)/g, "");
  out = out.replace(/(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{5,12}\b/g, "");
  return out.replace(/\s{2,}/g, " ").replace(/\s+([,.!?])/g, "$1").trim();
}

export function expandSpokenNumbers(text: string): string {
  if (!text || !/\d/.test(text)) return text;
  let out = text.replace(/\$\s*(\d[\d,]*(?:\.\d+)?)/g, (_m, n: string) => `dollars ${decimalWords(n)}`);
  out = out.replace(/(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)/gi, (_m, n: string) => `rupees ${decimalWords(n)}`);
  out = out.replace(
    /(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(lakh|lakhs|crore|crores)\b/gi,
    (_m, n: string, unit: string) => {
      const u = unit.toLowerCase().startsWith("lakh") ? "lakh" : "crore";
      return `${decimalWords(n)} ${u}`;
    }
  );
  out = out.replace(
    /(otp|pin|cvv|passcode|code)\b[^0-9]{0,16}(\d{4,6})(?!\d)/gi,
    (_m, label: string, digits: string) => `${label} ${[...digits].map((d) => ONES[Number(d)]).join(" ")}`
  );
  out = out.replace(
    /(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(paisa|rupees?|rs)\b/gi,
    (_m, n: string, unit: string) => `${decimalWords(n)} ${unit}`
  );
  out = out.replace(/\b(\d{1,2}):(\d{2})\s*(am|pm)?\b/gi, (_m, h: string, min: string, ap?: string) =>
    clockWords(Number(h), Number(min), ap || "")
  );
  out = out.replace(/\b((?:19|20)\d{2})\b/g, (_m, y: string) => yearWords(Number(y)));
  out = out.replace(/(?<!\d)(\d{7,9})(?!\d)/g, (_m, d: string) =>
    [...d].map((ch) => ONES[Number(ch)]).join(" ")
  );
  out = out.replace(/(?<!\d)(\d{3,6})(?!\d)/g, (m, digits: string, offset: number, full: string) => {
    const prefix = full.slice(Math.max(0, offset - 24), offset);
    if (/\b(plot|flat|unit|block|floor|phase)\s*$/i.test(prefix)) return digits;
    if (digits.length === 4 && /^(19|20)/.test(digits)) return yearWords(Number(digits));
    return decimalWords(digits);
  });
  return out;
}

const ABBREV_DOTS: Array<[RegExp, string]> = [
  [/\bRs\./gi, "rupees"],
  [/\bNo\./gi, "number"],
  [/\bDr\./gi, "Doctor"],
  [/\bMr\./gi, "Mister"],
  [/\bMrs\./gi, "Missus"],
  [/\bMs\./gi, "Miss"],
  [/\bLtd\./gi, "Limited"],
  [/\bInc\./gi, "Incorporated"],
  [/\bvs\./gi, "versus"],
  [/\be\.g\./gi, "for example"],
  [/\betc\./gi, "etcetera"],
];

const TERMINAL_PUNCT = new Set([".", "?", "!", "।", "！", "？"]);

/**
 * Prep text for Cartesia Sonic + Sarvam Bulbul.
 * Keep sentence punctuation (. ? ! ,) — both engines use it for pacing.
 * Only neutralize TTS-hostile dots: ellipses, abbreviations, bare decimals,
 * and letter.letter initialism separators.
 */
export function sanitizeTtsPunctuation(text: string, ensureTerminal = true): string {
  if (!text) return text;
  let out = text.replace(/\.{2,}/g, ",");
  for (const [pat, repl] of ABBREV_DOTS) out = out.replace(pat, repl);
  out = out.replace(/(?<!\d)(\d[\d,]*)\.(\d{1,4})(?!\d)/g, (_m, whole: string, frac: string) =>
    decimalWords(`${whole}.${frac}`)
  );
  // A.B → A B (not sentence periods)
  out = out.replace(/(?<=\b[A-Za-z])\.(?=[A-Za-z]\b)/g, " ");
  out = out.replace(/\s{2,}/g, " ").replace(/\s+([,.!?।])/g, "$1").replace(/^[, ]+|[, ]+$/g, "").trim();
  return ensureTerminal ? ensureTerminalPunctuation(out) : out;
}

export function ensureTerminalPunctuation(text: string): string {
  const cleaned = (text || "").trim();
  if (!cleaned) return cleaned;
  if (TERMINAL_PUNCT.has(cleaned[cleaned.length - 1]!)) return cleaned;
  return `${cleaned}.`;
}

export function prepareSpokenReply(text: string, options?: { ensureTerminal?: boolean }): string {
  return sanitizeTtsPunctuation(
    expandSpokenNumbers(stripSpokenPhoneNumbers(text || "")),
    options?.ensureTerminal !== false
  );
}

/** @deprecated use prepareSpokenReply */
export { prepareSpokenReply as expandSpokenNumbersForTts };
