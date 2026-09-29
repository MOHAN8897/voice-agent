"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * `/dev/saas-admin` was a single JSON dump. It is replaced by the `/dev/admin/*`
 * console, so this keeps old bookmarks working instead of 404ing.
 */
export default function SaasAdminRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dev/admin");
  }, [router]);
  return (
    <p className="p-6 text-sm text-text-muted" role="status">
      Moved to <span className="text-text">SaaS admin → Overview</span>…
    </p>
  );
}
