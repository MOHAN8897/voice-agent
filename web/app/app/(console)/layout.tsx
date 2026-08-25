import { AppAuthGate } from "@/components/auth/AppAuthGate";
import { ConsoleShell } from "@/components/console/ConsoleShell";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppAuthGate>
      <ConsoleShell>{children}</ConsoleShell>
    </AppAuthGate>
  );
}
