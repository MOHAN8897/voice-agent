import { DevShell } from "@/components/dev/DevShell";
import { DevPortalProvider } from "@/components/dev/DevPortalProvider";

export default function DevPortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <DevPortalProvider>
      <DevShell>{children}</DevShell>
    </DevPortalProvider>
  );
}
