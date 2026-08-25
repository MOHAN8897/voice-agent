import { AuthShell } from "@/components/auth/AuthShell";

export default function AuthRouteLayout({ children }: { children: React.ReactNode }) {
  return <AuthShell>{children}</AuthShell>;
}
