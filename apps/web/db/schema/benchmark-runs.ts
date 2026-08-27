import { jsonb, text, timestamp, varchar } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { benchmarks } from "./schemas";

/** A stored benchmark comparison of experiment-selection strategies. */
export const benchmarkRuns = benchmarks
  .table("benchmark_runs", {
    id: id(),
    status: varchar("status", { length: 20 }).notNull().default("RUNNING"),
    config: jsonb("config").$type<Record<string, unknown>>().notNull().default({}),
    results: jsonb("results").$type<Record<string, unknown>[]>(),
    summary: jsonb("summary").$type<Record<string, unknown>>(),
    error: text("error"),
    createdAt: createdAt(),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
  })
  .enableRLS();

export type BenchmarkRun = typeof benchmarkRuns.$inferSelect;
export type NewBenchmarkRun = typeof benchmarkRuns.$inferInsert;
