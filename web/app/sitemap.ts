import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_APP_URL || "https://voxly.ai";
  return [
    { url: `${base}/`, lastModified: new Date(), changeFrequency: "daily", priority: 1.0 },
    { url: `${base}/pricing`, lastModified: new Date(), changeFrequency: "weekly", priority: 0.9 },
    { url: `${base}/docs`, lastModified: new Date(), changeFrequency: "weekly", priority: 0.8 },
  ];
}
