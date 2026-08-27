/**
 * Browser-side store for the Better Auth bearer token, used to authenticate
 * direct browser → FastAPI requests (a different origin, so the session cookie
 * does not travel with them).
 */
const KEY = "gibbs.auth-token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(KEY, token);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}
