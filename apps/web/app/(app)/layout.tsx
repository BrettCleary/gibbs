import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { TopBar } from "@/components/TopBar";

/** Authenticated shell: verifies the session server-side, then renders the app chrome. */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");

  return (
    <div className="relative isolate">
      <div
        aria-hidden
        className="bg-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px]"
      />
      <TopBar user={{ email: session.user.email, name: session.user.name }} />
      <main className="mx-auto w-full max-w-[1400px] px-4 pb-16 pt-6 md:px-8 md:pt-8">
        {children}
      </main>
    </div>
  );
}
