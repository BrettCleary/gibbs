import { createApiClient } from "@alloylab/api-client";
import { getAuthToken } from "./auth-token";
import { signOut } from "./auth-client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createApiClient(API_URL);

api.use({
  onRequest({ request }) {
    const token = getAuthToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") {
      // Session expired or revoked: drop the (stale) cookie + token so the
      // middleware doesn't bounce us straight back, then go to the login page.
      const next = window.location.pathname + window.location.search;
      void signOut().finally(() =>
        window.location.assign(`/login?next=${encodeURIComponent(next)}`),
      );
    }
    return response;
  },
});

/** `fetch` against the API with the bearer token attached (for non-client paths like log downloads). */
export function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

/** URL for endpoints the browser must open without headers (EventSource): token goes in the query. */
export function apiUrlWithToken(path: string) {
  const token = getAuthToken();
  const sep = path.includes("?") ? "&" : "?";
  return token ? `${API_URL}${path}${sep}token=${encodeURIComponent(token)}` : `${API_URL}${path}`;
}
