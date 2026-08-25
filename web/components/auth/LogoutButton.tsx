"use client";

import { Button } from "@/components/ui/Button";
import { portalLogout, type PortalKind } from "@/lib/auth-client";

export function LogoutButton({
  kind,
  redirectTo,
  variant = "ghost",
  label = "Sign out",
}: {
  kind: PortalKind;
  redirectTo: string;
  variant?: "primary" | "secondary" | "ghost";
  label?: string;
}) {
  return (
    <Button
      type="button"
      variant={variant}
      onClick={() => portalLogout(kind, redirectTo)}
    >
      {label}
    </Button>
  );
}
