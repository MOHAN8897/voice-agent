import { redirect } from "next/navigation";

/** Merged into /dev/admin/billing (Wallet & rates). */
export default function AdminWalletsRedirect() {
  redirect("/dev/admin/billing");
}
