import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
import type { Metadata } from "next";
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

export const metadata: Metadata = {
  title: {
    default: "Vāṇi — Voice agents for Telugu-speaking businesses",
    template: "%s · Vāṇi",
  },
  description:
    "Configure business brains, test live voice, archive every call with memory and disposition — built for teams serving Telugu-speaking customers.",
  openGraph: {
    title: "Vāṇi — Voice agents for Telugu-speaking businesses",
    description: "Configure, test, and deploy production voice agents with memory.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-surface font-sans antialiased">{children}</body>
    </html>
  );
}
