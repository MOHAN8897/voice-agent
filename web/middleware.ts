import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const VOXLY_URL =
  process.env.VOXLY_DEV_URL || process.env.NEXT_PUBLIC_VOXLY_URL || "http://127.0.0.1:5173";

function redirectToVoxly(path = "/") {
  const base = VOXLY_URL.replace(/\/$/, "");
  const hash = path.startsWith("#") ? path : "";
  const pathname = hash ? "/" : path;
  return `${base}${pathname}${hash}`;
}

async function requireSession(
  request: NextRequest,
  kind: "dev",
  loginPath: string
): Promise<NextResponse | null> {
  const endpoint = "/api/auth/dev-me";
  try {
    const res = await fetch(`${API_URL}${endpoint}`, {
      headers: { cookie: request.headers.get("cookie") || "" },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (res.status === 401) {
      const login = new URL(loginPath, request.url);
      login.searchParams.set("next", request.nextUrl.pathname);
      return NextResponse.redirect(login);
    }
    if (!res.ok) {
      const login = new URL(loginPath, request.url);
      login.searchParams.set("error", "auth_check_failed");
      return NextResponse.redirect(login);
    }
  } catch {
    const login = new URL(loginPath, request.url);
    login.searchParams.set("error", "api_unavailable");
    return NextResponse.redirect(login);
  }
  return null;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Product UI lives in Voxly (Vite). Keep Next.js for dev portal + Test Studio only.
  if (
    pathname === "/" ||
    pathname.startsWith("/pricing") ||
    pathname.startsWith("/docs") ||
    pathname === "/login" ||
    pathname.startsWith("/app")
  ) {
    const dest =
      pathname.startsWith("/app") ? redirectToVoxly("#dashboard/overview") : redirectToVoxly("/");
    return NextResponse.redirect(dest);
  }

  if (pathname.startsWith("/dev")) {
    if (pathname.startsWith("/dev/login")) {
      return NextResponse.next();
    }
    const redirect = await requireSession(request, "dev", "/dev/login");
    return redirect ?? NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/pricing/:path*", "/docs/:path*", "/login", "/app/:path*", "/dev/:path*"],
};
