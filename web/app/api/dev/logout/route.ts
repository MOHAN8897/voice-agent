import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// POST only: a GET sign-out can be triggered by any <img> or link on another page.
async function proxyLogout(req: NextRequest) {
  const res = await fetch(`${API_URL}/api/dev/logout`, {
    method: "POST",
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
  return proxyLogout(req);
}
