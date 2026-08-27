import { index, jsonb, pgTable, timestamp, varchar } from "drizzle-orm/pg-core";
import { id } from "./_helpers";
import { campaigns } from "./campaigns";

/** One autonomous run of the scientist loop over a campaign. */
export const agentRuns = pgTable(
  "agent_runs",
  {
    id: id(),
    campaignId: varchar("campaign_id", { length: 32 })
      .notNull()
      .references(() => campaigns.id),
    model: varchar("model", { length: 100 }).notNull().default("heuristic"),
    status: varchar("status", { length: 20 }).notNull().default("RUNNING"),
    startedAt: timestamp("started_at", { withTimezone: true, mode: "date" }).defaultNow().notNull(),
    completedAt: timestamp("completed_at", { withTimezone: true, mode: "date" }),
    tokenUsage: jsonb("token_usage").$type<Record<string, unknown>>(),
  },
  (t) => [index("ix_agent_runs_campaign_id").on(t.campaignId)],
);

export type AgentRun = typeof agentRuns.$inferSelect;
export type NewAgentRun = typeof agentRuns.$inferInsert;
