/** @type {import('next').NextConfig} */
const apiUrl = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
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
