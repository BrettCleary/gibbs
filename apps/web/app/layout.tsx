import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "AlloyLab — Autonomous Materials Science",
  description:
    "Mission control for an autonomous computational materials scientist.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Providers>
          <header className="border-b border-[var(--border)] bg-[var(--panel-2)]">
            <div className="mx-auto flex max-w-7xl items-baseline gap-8 px-6 py-3">
              <Link href="/campaigns" className="mono text-sm font-bold tracking-widest text-[var(--accent)]">
                ALLOYLAB
              </Link>
              <nav className="flex gap-5 text-sm text-[var(--text-dim)]">
                <Link href="/campaigns" className="hover:text-[var(--text)]">
                  Campaigns
                </Link>
                <Link href="/benchmarks" className="hover:text-[var(--text)]">
                  Benchmarks
                </Link>
              </nav>
              <span className="ml-auto mono text-xs text-[var(--text-dim)]">
                V1 · autonomous alloy scientist
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
