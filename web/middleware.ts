import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function requireSession(
  request: NextRequest,
  kind: "app" | "dev",
  loginPath: string
): Promise<NextResponse | null> {
  const endpoint = kind === "dev" ? "/api/auth/dev-me" : "/api/auth/me";
  try {
    const res = await fetch(`${API_URL}${endpoint}`, {
      headers: { cookie: request.headers.get("cookie") || "" },
      cache: "no-store",
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

  if (pathname.startsWith("/dev")) {
    if (pathname.startsWith("/dev/login")) {
      return NextResponse.next();
    }
    const redirect = await requireSession(request, "dev", "/dev/login");
    return redirect ?? NextResponse.next();
  }

  if (
    !pathname.startsWith("/app") ||
    pathname.startsWith("/app/login") ||
    pathname.startsWith("/app/access-denied") ||
    pathname.startsWith("/app/select-tenant")
  ) {
    return NextResponse.next();
  }

  const redirect = await requireSession(request, "app", "/app/login");
  return redirect ?? NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*", "/dev/:path*"],
};
