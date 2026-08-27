import { doublePrecision, integer, jsonb, text, varchar } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { science } from "./schemas";

/** A discovery campaign (Ising V0, alloy V1, FCC V2, phase, DFT, property). */
export const campaigns = science.table("campaigns", {
  id: id(),
  name: varchar("name", { length: 200 }).notNull(),
  objective: text("objective").notNull(),
  problemType: varchar("problem_type", { length: 50 }).notNull().default("ising_v0"),
  strategy: varchar("strategy", { length: 50 }).notNull().default("agent"),

  // Search space (temperature in problem units; composition for alloy problems).
  temperatureMin: doublePrecision("temperature_min").notNull().default(1.5),
  temperatureMax: doublePrecision("temperature_max").notNull().default(3.5),
  compositionMin: doublePrecision("composition_min"),
  compositionMax: doublePrecision("composition_max"),
  elements: jsonb("elements").$type<string[]>().notNull().default([]),

  latticeSize: integer("lattice_size").notNull().default(24),
  simulationBudget: integer("simulation_budget").notNull().default(20),
  simulationsUsed: integer("simulations_used").notNull().default(0),
  targetUncertainty: doublePrecision("target_uncertainty"),
  failureRate: doublePrecision("failure_rate").notNull().default(0),

  status: varchar("status", { length: 30 }).notNull().default("CREATED"),
  stoppingRationale: text("stopping_rationale"),
  /** Hidden problem definition (e.g. the secret Hamiltonian). Never exposed via the API. */
  problemConfig: jsonb("problem_config").$type<Record<string, unknown>>(),
  /** Final scientific report, persisted at completion. */
  report: jsonb("report").$type<Record<string, unknown>>(),
  createdAt: createdAt(),
}).enableRLS();

export type Campaign = typeof campaigns.$inferSelect;
export type NewCampaign = typeof campaigns.$inferInsert;
