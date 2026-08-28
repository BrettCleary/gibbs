import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { AppShell } from "@/components/AppShell";

/** Authenticated shell: verifies the session server-side, then renders the app chrome. */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");

  return (
    <AppShell user={{ email: session.user.email, name: session.user.name }}>{children}</AppShell>
  );
}
