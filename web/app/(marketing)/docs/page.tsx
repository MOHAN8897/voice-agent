import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documentation",
  description: "API reference and integration guide for the Vāṇi voice platform.",
};

const SECTIONS = [
  {
    title: "Quick start",
    links: [
      { label: "Open Business Console", href: "/app" },
      { label: "Create & configure agent", href: "/app/agents" },
      { label: "Run Test Studio", href: "/app/test-studio" },
    ],
  },
  {
    title: "Call lifecycle API",
    links: [
      { label: "POST /api/call/start", href: "#" },
      { label: "POST /api/call/end", href: "#" },
      { label: "GET /api/calls", href: "#" },
      { label: "GET /api/call/{id}/transcript", href: "#" },
    ],
  },
  {
    title: "Realtime",
    links: [
      { label: "WS /ws/stt-realtime", href: "#" },
      { label: "POST /api/brain/stream", href: "#" },
      { label: "WS /ws/tts", href: "#" },
    ],
  },
];

export default function DocsPage() {
  return (
    <main className="py-20">
      <div className="mx-auto max-w-content px-6">
        <div className="max-w-2xl">
          <p className="label-caps text-accent">Documentation</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-text">Build on Vāṇi</h1>
          <p className="mt-4 text-lg text-text-muted">
            REST and WebSocket contracts for calls, brains, memory, and telephony.
          </p>
        </div>

        <div className="mt-16 grid gap-6 sm:grid-cols-2">
          {SECTIONS.map((section) => (
            <section key={section.title} className="card-surface p-6">
              <h2 className="font-semibold text-text">{section.title}</h2>
              <ul className="mt-4 space-y-2">
                {section.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="font-mono text-sm text-text-muted transition-colors hover:text-accent"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
