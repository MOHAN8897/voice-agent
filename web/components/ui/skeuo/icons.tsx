/** Minimal line icons for instrument-panel navigation — no emoji, no cartoon. */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export function IconOverview(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <rect x="2.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="2.5" y="11.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="11.5" width="6" height="6" rx="1" />
    </svg>
  );
}

export function IconAgents(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <circle cx="7" cy="7" r="3" />
      <path d="M2 17c0-2.8 2.2-5 5-5s5 2.2 5 5" />
      <circle cx="14" cy="6" r="2.5" />
      <path d="M12 17c0-2 1.5-3.5 3.5-3.5" />
    </svg>
  );
}

export function IconMic(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <rect x="7" y="3" width="6" height="9" rx="3" />
      <path d="M4 10a6 6 0 0 0 12 0M10 16v2" />
    </svg>
  );
}

export function IconCalls(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <path d="M4 4h12v10H4z" />
      <path d="M7 14v3h6v-3" />
    </svg>
  );
}

export function IconChart(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <path d="M3 16V8M8 16V4M13 16v-6M18 16v-9" />
    </svg>
  );
}

export function IconBenchmark(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <path d="M4 15l4-6 3 4 5-8" />
      <circle cx="16" cy="5" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconRack(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <rect x="3" y="3" width="14" height="4" rx="1" />
      <rect x="3" y="9" width="14" height="4" rx="1" />
      <circle cx="6" cy="5" r="1" fill="currentColor" stroke="none" />
      <circle cx="6" cy="11" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconPlug(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <path d="M7 8V4M13 8V4M5 8h10v5a2 2 0 0 1-2 2h-1v3M8 15h4" />
    </svg>
  );
}

export function IconSettings(props: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden {...props}>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4" />
    </svg>
  );
}
