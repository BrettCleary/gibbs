import { NextRequest, NextResponse } from "next/server";
import { getSessionCookie } from "better-auth/cookies";

/**
 * Optimistic auth gate: redirects to /login when no session cookie is present.
 * The real check (session lookup) happens in app/(app)/layout.tsx.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(getSessionCookie(request));

  if (pathname === "/login") {
    if (hasSession) return NextResponse.redirect(new URL("/campaigns", request.url));
    return NextResponse.next();
  }
  if (!hasSession) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname + request.nextUrl.search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the auth API, Next internals, and static assets.
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|ico|webp)$).*)",
  ],
};
