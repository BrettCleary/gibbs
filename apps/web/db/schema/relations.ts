import { relations } from "drizzle-orm";
import { agentEvents } from "./agent-events";
import { agentRuns } from "./agent-runs";
import { calculations } from "./calculations";
import { campaigns } from "./campaigns";
import { structures } from "./structures";
import { surrogateModels } from "./surrogate-models";

export const campaignsRelations = relations(campaigns, ({ many }) => ({
  structures: many(structures),
  calculations: many(calculations),
  surrogateModels: many(surrogateModels),
  agentRuns: many(agentRuns),
  agentEvents: many(agentEvents),
}));

export const structuresRelations = relations(structures, ({ one, many }) => ({
  campaign: one(campaigns, { fields: [structures.campaignId], references: [campaigns.id] }),
  calculations: many(calculations),
}));

export const calculationsRelations = relations(calculations, ({ one, many }) => ({
  campaign: one(campaigns, { fields: [calculations.campaignId], references: [campaigns.id] }),
  structure: one(structures, { fields: [calculations.structureId], references: [structures.id] }),
  retryOf: one(calculations, {
    fields: [calculations.retryOf],
    references: [calculations.id],
    relationName: "retries",
  }),
  retries: many(calculations, { relationName: "retries" }),
}));

export const surrogateModelsRelations = relations(surrogateModels, ({ one }) => ({
  campaign: one(campaigns, { fields: [surrogateModels.campaignId], references: [campaigns.id] }),
}));

export const agentRunsRelations = relations(agentRuns, ({ one, many }) => ({
  campaign: one(campaigns, { fields: [agentRuns.campaignId], references: [campaigns.id] }),
  events: many(agentEvents),
}));

export const agentEventsRelations = relations(agentEvents, ({ one }) => ({
  campaign: one(campaigns, { fields: [agentEvents.campaignId], references: [campaigns.id] }),
  agentRun: one(agentRuns, { fields: [agentEvents.agentRunId], references: [agentRuns.id] }),
}));
