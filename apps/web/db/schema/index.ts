/**
 * Drizzle schema — the source of truth for the AlloyLab database.
 *
 * Migrations are generated from these files with `pnpm --filter @alloylab/web
 * db:generate` (drizzle-kit) into apps/web/migrations and applied to Supabase
 * Postgres with `db:migrate`. The Python API (SQLAlchemy over asyncpg) maps
 * the same tables for its queries and never creates tables in Postgres.
 */
export * from "./campaigns";
export * from "./structures";
export * from "./calculations";
export * from "./surrogate-models";
export * from "./agent-runs";
export * from "./agent-events";
export * from "./benchmark-runs";
export * from "./relations";
