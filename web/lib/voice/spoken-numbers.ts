/** Conservative leftover-digit expander. Mirror of server/services/spoken_numbers.py. */

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

function digitWords(digits: string): string {
  return [...digits].filter((ch) => /\d/.test(ch)).map((ch) => ONES[Number(ch)]).join(" ");
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

export function expandSpokenNumbers(text: string): string {
  if (!text || !/\d/.test(text)) return text;
  let out = text.replace(/(?<!\d)(?:\+91[-\s]?)?(\d{10})(?!\d)/g, (_, d: string) => digitWords(d));
  out = out.replace(
    /(otp|pin|cvv|passcode|code)\b[^0-9]{0,16}(\d{4,6})(?!\d)/gi,
    (_m, label: string, digits: string) => `${label} ${digitWords(digits)}`
  );
  out = out.replace(/(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)/gi, (_m, n: string) => decimalWords(n));
  out = out.replace(
    /(?<!\d)(\d[\d,]*(?:\.\d+)?)\s*(paisa|rupees?|lakh|lakhs|crore|crores|rs)\b/gi,
    (_m, n: string, unit: string) => `${decimalWords(n)} ${unit}`
  );
  out = out.replace(/\b(\d{1,2}):(\d{2})\s*(am|pm)?\b/gi, (_m, h: string, min: string, ap?: string) =>
    clockWords(Number(h), Number(min), ap || "")
  );
  out = out.replace(/\b((?:19|20)\d{2})\b/g, (_m, y: string) => yearWords(Number(y)));
  out = out.replace(/(?<!\d)(\d{7,9})(?!\d)/g, (_m, d: string) => digitWords(d));
  out = out.replace(/(?<!\d)(\d{3,6})(?!\d)/g, (m, digits: string, offset: number, full: string) => {
    const prefix = full.slice(Math.max(0, offset - 24), offset);
    if (/\b(plot|flat|unit|block|floor|phase)\s*$/i.test(prefix)) return digits;
    if (digits.length === 4 && /^(19|20)/.test(digits)) return yearWords(Number(digits));
    return decimalWords(digits);
  });
  return out;
}
