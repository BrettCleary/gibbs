import { index, integer, jsonb, pgTable, varchar } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { campaigns } from "./campaigns";

/** A fitted surrogate: response surrogate, cluster expansion, phase boundary, ... */
export const surrogateModels = pgTable(
  "surrogate_models",
  {
    id: id(),
    campaignId: varchar("campaign_id", { length: 32 })
      .notNull()
      .references(() => campaigns.id),
    type: varchar("type", { length: 50 }).notNull().default("response_surrogate"),
    version: integer("version").notNull().default(1),
    trainingCalculationIds: jsonb("training_calculation_ids").$type<string[]>().notNull().default([]),
    parameters: jsonb("parameters").$type<Record<string, unknown>>().notNull().default({}),
    validationMetrics: jsonb("validation_metrics").$type<Record<string, unknown>>().notNull().default({}),
    artifact: jsonb("artifact").$type<Record<string, unknown>>().notNull().default({}),
    createdAt: createdAt(),
  },
  (t) => [index("ix_surrogate_models_campaign_id").on(t.campaignId)],
);

export type SurrogateModel = typeof surrogateModels.$inferSelect;
export type NewSurrogateModel = typeof surrogateModels.$inferInsert;
