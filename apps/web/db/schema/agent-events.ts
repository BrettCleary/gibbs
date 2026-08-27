import { index, jsonb, text, varchar } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { agent } from "./schemas";
import { agentRuns } from "./agent-runs";
import { campaigns } from "./campaigns";

/** Auditable record of every agent decision/action and job lifecycle event. */
export const agentEvents = agent.table(
  "agent_events",
  {
    id: id(),
    agentRunId: varchar("agent_run_id", { length: 32 }).references(() => agentRuns.id),
    campaignId: varchar("campaign_id", { length: 32 })
      .notNull()
      .references(() => campaigns.id),
    eventType: varchar("event_type", { length: 50 }).notNull(),
    hypothesis: text("hypothesis"),
    reasoningSummary: text("reasoning_summary"),
    action: text("action"),
    toolName: varchar("tool_name", { length: 100 }),
    toolInput: jsonb("tool_input").$type<Record<string, unknown>>(),
    toolOutputReference: varchar("tool_output_reference", { length: 200 }),
    payload: jsonb("payload").$type<Record<string, unknown>>(),
    createdAt: createdAt(),
  },
  (t) => [
    index("ix_agent_events_campaign_id").on(t.campaignId),
    index("ix_agent_events_event_type").on(t.eventType),
  ],
).enableRLS();

export type AgentEvent = typeof agentEvents.$inferSelect;
export type NewAgentEvent = typeof agentEvents.$inferInsert;
