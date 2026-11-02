import { wsUrl } from "@/lib/api";

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/**
 * Voice sockets (/ws/stt-realtime, /ws/tts) authenticate with the dev_session cookie,
 * which is host-only: a page on localhost:3000 never sends it to 127.0.0.1:8000.
 * Keep the API port but use the page's own loopback hostname so the cookie rides
 * along on the upgrade.
 */
export function cookieWsUrl(path: string): string {
  const url = wsUrl(path);
  if (typeof window === "undefined") return url;
  try {
    const target = new URL(url);
    const page = window.location.hostname;
    if (LOOPBACK.has(target.hostname) && LOOPBACK.has(page) && target.hostname !== page) {
      target.hostname = page;
      return target.toString();
    }
  } catch {
    /* keep wsUrl */
  }
  return url;
}
