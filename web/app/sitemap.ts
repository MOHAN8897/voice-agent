import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_APP_URL || "https://www.dialtact.com";
  // The public product sitemap is served by Dialtact; this app is the admin portal.
  return [];
}
