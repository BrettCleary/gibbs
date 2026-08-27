import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { TopBar } from "@/components/TopBar";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AlloyLab — Autonomous Materials Science",
  description: "Mission control for an autonomous computational materials scientist.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body className="min-h-screen bg-bg">
        <Providers>
          <div className="relative isolate">
            <div aria-hidden className="bg-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px]" />
            <TopBar />
            <main className="mx-auto w-full max-w-[1400px] px-4 pb-16 pt-6 md:px-8 md:pt-8">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
