import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function proxyLogout(req: NextRequest, method: "POST" | "GET") {
  const res = await fetch(`${API_URL}/api/app/logout`, {
    method,
    headers: { cookie: req.headers.get("cookie") || "" },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({ ok: true }));
  const out = NextResponse.json(data, { status: res.status });
  const setCookies = res.headers.getSetCookie?.() ?? [];
  if (setCookies.length) {
    for (const c of setCookies) {
      out.headers.append("Set-Cookie", c);
    }
  } else {
    const legacy = res.headers.get("set-cookie");
    if (legacy) out.headers.set("set-cookie", legacy);
  }
  return out;
}

export async function POST(req: NextRequest) {
  return proxyLogout(req, "POST");
}

export async function GET(req: NextRequest) {
  return proxyLogout(req, "GET");
}
