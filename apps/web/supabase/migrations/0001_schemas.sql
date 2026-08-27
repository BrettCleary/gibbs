-- Move the application tables out of `public` into domain schemas and enable
-- row-level security. SET SCHEMA preserves data, constraints, and indexes.
-- Supabase's REST layer exposes only `public`, so these tables are no longer
-- reachable with the anon key.
CREATE SCHEMA "agent";
--> statement-breakpoint
CREATE SCHEMA "benchmarks";
--> statement-breakpoint
CREATE SCHEMA "science";
--> statement-breakpoint
ALTER TABLE "public"."agent_events" SET SCHEMA "agent";
--> statement-breakpoint
ALTER TABLE "public"."agent_runs" SET SCHEMA "agent";
--> statement-breakpoint
ALTER TABLE "public"."benchmark_runs" SET SCHEMA "benchmarks";
--> statement-breakpoint
ALTER TABLE "public"."calculations" SET SCHEMA "science";
--> statement-breakpoint
ALTER TABLE "public"."campaigns" SET SCHEMA "science";
--> statement-breakpoint
ALTER TABLE "public"."structures" SET SCHEMA "science";
--> statement-breakpoint
ALTER TABLE "public"."surrogate_models" SET SCHEMA "science";
--> statement-breakpoint
ALTER TABLE "science"."campaigns" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "science"."structures" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "science"."calculations" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "science"."surrogate_models" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "agent"."agent_runs" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "agent"."agent_events" ENABLE ROW LEVEL SECURITY;
--> statement-breakpoint
ALTER TABLE "benchmarks"."benchmark_runs" ENABLE ROW LEVEL SECURITY;
