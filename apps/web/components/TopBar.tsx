"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { signOut } from "@/lib/auth-client";
import { cn } from "@/lib/cn";
import { IconButton, StatusDot, TechnicalLabel } from "@/components/ui/primitives";

const NAV = [
  { href: "/campaigns", label: "Campaigns" },
  { href: "/benchmarks", label: "Benchmarks" },
];

export function TopBar({ user }: { user: { email: string; name: string } }) {
  const pathname = usePathname();
  const router = useRouter();

  // Lightweight liveness probe: reuses the campaigns list the pages already fetch.
  const live = useQuery({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns");
      return data ?? [];
    },
    refetchInterval: 5000,
  });
  const nRunning = (live.data ?? []).filter((c) => c.status === "RUNNING").length;
  const apiTone = live.isError ? "bad" : live.data ? "good" : "neutral";

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-12 w-full max-w-[1400px] items-center gap-6 px-4 md:px-8">
        <Link
          href="/campaigns"
          className="group flex items-center gap-2.5 rounded-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Mark />
          <span className="font-mono text-[12px] font-medium tracking-[0.22em] text-text">
            ALLOYLAB
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-sm px-2.5 py-1.5 text-[13px] transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                  active ? "text-text" : "text-text-secondary hover:text-text",
                )}
              >
                {item.label}
                {active && <span className="absolute inset-x-2.5 -bottom-[13px] h-px bg-accent" />}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto hidden items-center gap-5 sm:flex">
          {nRunning > 0 && (
            <span className="flex items-center gap-2 font-mono text-[11px] text-accent-bright">
              <StatusDot tone="accent" pulse />
              {nRunning} running
            </span>
          )}
          <span className="flex items-center gap-2">
            <StatusDot tone={apiTone} />
            <TechnicalLabel>
              {live.isError ? "api offline" : live.data ? "api online" : "connecting"}
            </TechnicalLabel>
          </span>
          <span className="flex items-center gap-2 border-l border-line pl-5">
            <span className="font-mono text-[11px] text-text-secondary" title={user.name}>
              {user.email}
            </span>
            <IconButton
              label="Sign out"
              onClick={async () => {
                await signOut();
                router.replace("/login");
                router.refresh();
              }}
            >
              <LogOut className="h-3.5 w-3.5" />
            </IconButton>
          </span>
        </div>
      </div>
    </header>
  );
}

/** Wordmark glyph: an FCC-ish lattice motif. */
function Mark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden className="text-accent">
      <rect
        x="1.5"
        y="1.5"
        width="15"
        height="15"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
        opacity="0.5"
      />
      <circle cx="1.5" cy="1.5" r="1.6" fill="currentColor" />
      <circle cx="16.5" cy="1.5" r="1.6" fill="currentColor" />
      <circle cx="1.5" cy="16.5" r="1.6" fill="currentColor" />
      <circle cx="16.5" cy="16.5" r="1.6" fill="currentColor" />
      <circle cx="9" cy="9" r="2" fill="currentColor" className="text-text" />
    </svg>
  );
}
