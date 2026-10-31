/** @type {import('next').NextConfig} */
const apiUrl = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'; object-src 'none'; base-uri 'self'" },
      { key: "X-Robots-Tag", value: "noindex, nofollow" },
    ] }];
  },
  // Keep development output separate from the production bundle used by share.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Share/CI: typecheck+eslint during `next build` has hung on Windows in this repo.
  // Run `npm run lint` separately when needed.
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/ws/:path*", destination: `${apiUrl}/ws/:path*` },
    ];
  },
};

export default nextConfig;
