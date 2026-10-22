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

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_APP_URL || "https://www.dialtact.com";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#0F0E17",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Dialtact — AI Voice Agents for Customer Calls",
    template: "%s · Dialtact",
  },
  description:
    "Configure business brains, test live voice, archive every call with memory and disposition — built for teams serving customers with autonomous voice AI.",
  keywords: [
    "Telugu voice agent",
    "AI telecaller",
    "Telugu speech AI",
    "AI receptionist",
    "voice bot",
    "autonomous telephony",
    "Dialtact",
    "Dialtact AI",
  ],
  authors: [{ name: "Dialtact" }],
  creator: "Dialtact",
  publisher: "Dialtact",
  alternates: {
    canonical: "/",
  },
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  openGraph: {
    title: "Dialtact — AI Voice Agents for Customer Calls",
    description: "Configure, test, and deploy production voice agents with memory.",
    type: "website",
    url: siteUrl,
    siteName: "Dialtact",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Dialtact — AI Voice Agents for Customer Calls",
    description: "Configure, test, and deploy production voice agents with memory.",
    creator: "@dialtact",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-surface font-sans antialiased">{children}</body>
    </html>
  );
}
