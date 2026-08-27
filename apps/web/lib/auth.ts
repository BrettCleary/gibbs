import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/next-js";
import { bearer } from "better-auth/plugins";
import { getDb, schema } from "@/db";

/**
 * Better Auth server instance — email + password only, no email verification.
 *
 * The `bearer` plugin echoes the signed session token in a `set-auth-token`
 * response header on sign-in; the browser stores it and sends it as
 * `Authorization: Bearer …` to the FastAPI backend, which validates it
 * against the shared `app_auth.session` table.
 */
export const auth = betterAuth({
  baseURL:
    process.env.BETTER_AUTH_URL ?? process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
  secret: process.env.BETTER_AUTH_SECRET,
  database: drizzleAdapter(getDb(), {
    provider: "pg",
    schema: {
      user: schema.user,
      session: schema.session,
      account: schema.account,
      verification: schema.verification,
    },
  }),
  emailAndPassword: {
    enabled: true,
    requireEmailVerification: false,
    minPasswordLength: 8,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 30, // 30 days
    updateAge: 60 * 60 * 24,
  },
  plugins: [bearer(), nextCookies()],
});

export type Auth = typeof auth;
