import { AuthShell } from "@/components/auth/AuthShell";

export default function DevAuthLayout({ children }: { children: React.ReactNode }) {
  return <AuthShell variant="dev">{children}</AuthShell>;
}
