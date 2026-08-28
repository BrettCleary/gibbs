/**
 * Drizzle schema — the source of truth for the Gibbs database.
 *
 * Migrations are generated from these files with `pnpm --filter @gibbs/web
 * db:generate` (drizzle-kit) into apps/web/migrations and applied to Supabase
 * Postgres with `db:migrate`. The Python API (SQLAlchemy over asyncpg) maps
 * the same tables for its queries and never creates tables in Postgres.
 *
 * Tables live in the `science`, `agent`, `benchmarks`, and `app_auth` Postgres schemas
 * (never `public`) with RLS enabled — see schemas.ts.
 */
export * from "./schemas";
export * from "./campaigns";
export * from "./structures";
export * from "./calculations";
export * from "./surrogate-models";
export * from "./agent-runs";
export * from "./agent-events";
export * from "./benchmark-runs";
export * from "./copilot";
export * from "./agent-config";
export * from "./relations";
export * from "./auth";
