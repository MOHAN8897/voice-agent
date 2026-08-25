import type { Metadata } from "next";
import { HomeExperience } from "@/components/marketing/home/HomeExperience";

export const metadata: Metadata = {
  title: "Voice agents for Telugu-speaking businesses",
  description:
    "Configure a Business Brain, test live, archive every call with memory and disposition. Built for teams serving Telugu-speaking customers.",
};

export default function HomePage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Vāṇi",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description: "Voice control plane for businesses serving Telugu-speaking customers.",
    offers: { "@type": "Offer", price: "0", priceCurrency: "INR" },
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <HomeExperience />
    </>
  );
}
