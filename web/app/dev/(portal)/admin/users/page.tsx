import { redirect } from "next/navigation";

export default async function AdminUsersRoute({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    for (const item of Array.isArray(value) ? value : value ? [value] : []) params.append(key, item);
  }
  params.set("section", "users");
  redirect(`/dev/admin/tenants?${params}`);
}
