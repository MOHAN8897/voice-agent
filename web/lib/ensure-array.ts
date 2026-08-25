/** Coerce API values that should be arrays — avoids `.map is not a function`. */
export function ensureArray<T>(value: unknown, fallback: T[] = []): T[] {
  if (Array.isArray(value)) return value as T[];
  return fallback;
}
