import { index, jsonb, pgTable, text, timestamp, varchar, type AnyPgColumn } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { campaigns } from "./campaigns";
import { structures } from "./structures";

/**
 * One simulation job: Monte Carlo run, oracle energy query, or a real
 * DFT/EMT calculation. Strongly typed — the agent never runs shell commands.
 */
export const calculations = pgTable(
  "calculations",
  {
    id: id(),
    campaignId: varchar("campaign_id", { length: 32 })
      .notNull()
      .references(() => campaigns.id),
    structureId: varchar("structure_id", { length: 32 }).references(() => structures.id),
    calculationType: varchar("calculation_type", { length: 40 }).notNull().default("MONTE_CARLO"),
    engine: varchar("engine", { length: 100 }).notNull().default("alloyscience.ising.IsingSimulator"),
    status: varchar("status", { length: 20 }).notNull().default("QUEUED"),

    inputParameters: jsonb("input_parameters").$type<Record<string, unknown>>().notNull().default({}),
    output: jsonb("output").$type<Record<string, unknown>>(),
    provenance: jsonb("provenance").$type<Record<string, unknown>>(),

    failureCategory: varchar("failure_category", { length: 60 }),
    failureMetadata: jsonb("failure_metadata").$type<Record<string, unknown>>(),
    /** Self-reference: the failed calculation this one retries. */
    retryOf: varchar("retry_of", { length: 32 }).references((): AnyPgColumn => calculations.id),
    changedParameters: jsonb("changed_parameters").$type<Record<string, unknown>>(),
    reasonForChange: text("reason_for_change"),
    /** null | "retried" | "abandoned" — how a FAILED calculation was dealt with. */
    resolution: varchar("resolution", { length: 20 }),
    /** Engine log artifacts (e.g. the pw.x .pwo file). */
    stdoutArtifact: varchar("stdout_artifact", { length: 500 }),
    stderrArtifact: varchar("stderr_artifact", { length: 500 }),

    createdAt: createdAt(),
    startedAt: timestamp("started_at", { withTimezone: true, mode: "date" }),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
  },
  (t) => [
    index("ix_calculations_campaign_id").on(t.campaignId),
    index("ix_calculations_structure_id").on(t.structureId),
    index("ix_calculations_status").on(t.status),
  ],
);

export type Calculation = typeof calculations.$inferSelect;
export type NewCalculation = typeof calculations.$inferInsert;
