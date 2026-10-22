import { NextRequest } from "next/server";

const API_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

// Script generation may use a structured attempt followed by a plain-text
// fallback. Keep this route above the generic rewrite's 30-second proxy limit.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const UPSTREAM_TIMEOUT_MS = 110_000;

async function proxyInstructions(
  request: NextRequest,
  method: "GET" | "POST" | "DELETE"
): Promise<Response> {
  const target = new URL("/api/instructions", API_URL);
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });

  const headers = new Headers();
  for (const name of ["authorization", "content-type", "cookie"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body: method === "POST" ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: controller.signal,
    });

    const responseHeaders = new Headers();
    for (const name of ["cache-control", "content-type", "set-cookie"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut =
      error instanceof Error &&
      (error.name === "AbortError" || error.name === "TimeoutError");
    return Response.json(
      {
        detail: {
          error: {
            code: timedOut ? "agent_script_timeout" : "instructions_upstream_unavailable",
            message: timedOut
              ? "Agent script generation timed out. Please try again."
              : "The agent service is temporarily unavailable. Please try again.",
          },
        },
      },
      { status: timedOut ? 504 : 502 }
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function GET(request: NextRequest) {
  return proxyInstructions(request, "GET");
}

export function POST(request: NextRequest) {
  return proxyInstructions(request, "POST");
}

export function DELETE(request: NextRequest) {
  return proxyInstructions(request, "DELETE");
}
