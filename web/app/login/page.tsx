import { redirect } from "next/navigation";

/** Public shortcut — business console login lives at /app/login */
export default function LoginRedirectPage() {
  redirect("/app/login");
}
