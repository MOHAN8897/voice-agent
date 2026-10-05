import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
import type { Metadata, Viewport } from "next";
import "./globals.css";

const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_APP_URL || "https://voxly.ai";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#0F0E17",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Vāṇi — Voice agents for Telugu-speaking businesses",
    template: "%s · Vāṇi",
  },
  description:
    "Configure business brains, test live voice, archive every call with memory and disposition — built for teams serving Telugu-speaking customers.",
  keywords: [
    "Telugu voice agent",
    "AI telecaller",
    "Telugu speech AI",
    "AI receptionist",
    "voice bot",
    "autonomous telephony",
    "Vāṇi AI",
  ],
  authors: [{ name: "Voxly AI" }],
  creator: "Voxly AI",
  publisher: "Voxly AI",
  alternates: {
    canonical: "/",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  openGraph: {
    title: "Vāṇi — Voice agents for Telugu-speaking businesses",
    description: "Configure, test, and deploy production voice agents with memory.",
    type: "website",
    url: siteUrl,
    siteName: "Vāṇi",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Vāṇi — Voice agents for Telugu-speaking businesses",
    description: "Configure, test, and deploy production voice agents with memory.",
    creator: "@voxlyai",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-surface font-sans antialiased">{children}</body>
    </html>
  );
}
