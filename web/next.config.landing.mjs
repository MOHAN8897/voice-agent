/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "export",
  distDir: "out-landing",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
