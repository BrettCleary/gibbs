import { pgSchema } from "drizzle-orm/pg-core";

/**
 * Postgres schemas — kept OUT of `public` so Supabase's REST layer does not
 * expose them to anon-key clients (only `public`/`graphql_public` are exposed
 * by default). The split mirrors the codebase's layers.
 */
export const science = pgSchema("science"); // campaigns, structures, calculations, surrogate models
export const agent = pgSchema("agent"); // agent runs and the decision/event trail
export const benchmarks = pgSchema("benchmarks"); // strategy benchmark runs
export const appAuth = pgSchema("app_auth"); // Better Auth users/sessions (Supabase owns `auth`)
