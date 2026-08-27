"use client";

import { createAuthClient } from "better-auth/react";
import { setAuthToken } from "./auth-token";

export const authClient = createAuthClient({
  fetchOptions: {
    onSuccess(ctx) {
      // Set by the server's `bearer` plugin on sign-in / sign-up / session refresh.
      const token = ctx.response.headers.get("set-auth-token");
      if (token) setAuthToken(token);
    },
  },
});

export async function signOut() {
  setAuthToken(null);
  await authClient.signOut();
}

export const { useSession, signIn, signUp } = authClient;
