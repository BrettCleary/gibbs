import {
  boolean,
  foreignKey,
  index,
  integer,
  jsonb,
  primaryKey,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import { agent } from "./schemas";
import { messages } from "./copilot";

/**
 * Agent configuration model (after coinfello): an agent row names a system
 * prompt and a model and is composed from tool sets (which tools it may call)
 * and skill sets (documents it may load on demand with `load_skill`).
 * Which skills a message actually loaded is recorded in message_skill so the
 * conversation can be rebuilt faithfully.
 */

const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const agentConfig = agent
  .table("agent_config", {
    id: serial("id").primaryKey(),
    maxOutputTokens: integer("max_output_tokens").notNull().default(4096),
    /** Stored ×100 (e.g. 20 = 0.2); null = provider default. */
    temperature: integer("temperature"),
    topP: integer("top_p"),
    /** Pydantic AI model_settings passthrough, keyed by provider. */
    providerOptions: jsonb("provider_options")
      .$type<Record<string, Record<string, unknown>>>()
      .notNull()
      .default({}),
    baseUrl: text("base_url"),
    createdAt: ts("created_at").notNull().defaultNow(),
    updatedAt: ts("updated_at").notNull().defaultNow(),
  })
  .enableRLS();

export const agents = agent
  .table("agent", {
    id: serial("id").primaryKey(),
    /** Stable handle the API resolves, e.g. "copilot". */
    name: text("name").notNull().unique(),
    systemPrompt: text("system_prompt").notNull(),
    /** Pydantic AI model string, e.g. "openai:gpt-5"; null = ALLOYLAB_AGENT_MODEL. */
    foundationModel: text("foundation_model"),
    enableAllTools: boolean("enable_all_tools").notNull().default(false),
    agentConfigId: integer("agent_config_id")
      .notNull()
      .references(() => agentConfig.id),
    tag: text("tag"),
    description: text("description"),
    createdAt: ts("created_at").notNull().defaultNow(),
    updatedAt: ts("updated_at").notNull().defaultNow(),
  })
  .enableRLS();

// Tool sets

export const toolSet = agent
  .table("tool_set", {
    id: serial("id").primaryKey(),
    name: text("name").notNull().unique(),
    description: text("description"),
    createdAt: ts("created_at").notNull().defaultNow(),
    updatedAt: ts("updated_at").notNull().defaultNow(),
  })
  .enableRLS();

export const toolSetTool = agent
  .table(
    "tool_set_tool",
    {
      toolSetId: integer("tool_set_id")
        .notNull()
        .references(() => toolSet.id, { onDelete: "cascade" }),
      /** Name of a tool registered in code (gibbs/copilot/agent.py). */
      toolName: text("tool_name").notNull(),
    },
    (t) => [
      primaryKey({ columns: [t.toolSetId, t.toolName] }),
      index("tool_set_tool_tool_name_idx").on(t.toolName),
    ],
  )
  .enableRLS();

export const agentToolSet = agent
  .table(
    "agent_tool_set",
    {
      agentId: integer("agent_id")
        .notNull()
        .references(() => agents.id, { onDelete: "cascade" }),
      toolSetId: integer("tool_set_id")
        .notNull()
        .references(() => toolSet.id, { onDelete: "cascade" }),
      createdAt: ts("created_at").notNull().defaultNow(),
    },
    (t) => [primaryKey({ columns: [t.agentId, t.toolSetId] })],
  )
  .enableRLS();

// Skill sets

export const skillSet = agent
  .table("skill_set", {
    id: serial("id").primaryKey(),
    name: text("name").notNull().unique(),
    description: text("description"),
    createdAt: ts("created_at").notNull().defaultNow(),
    updatedAt: ts("updated_at").notNull().defaultNow(),
  })
  .enableRLS();

export const skillSetSkill = agent
  .table(
    "skill_set_skill",
    {
      skillSetId: integer("skill_set_id")
        .notNull()
        .references(() => skillSet.id, { onDelete: "cascade" }),
      skillName: text("skill_name").notNull(),
      /** One line shown to the model so it can decide whether to load the skill. */
      description: text("description"),
      /** The skill body (markdown), returned by load_skill. */
      content: text("content").notNull(),
    },
    (t) => [
      primaryKey({ columns: [t.skillSetId, t.skillName] }),
      index("skill_set_skill_skill_name_idx").on(t.skillName),
    ],
  )
  .enableRLS();

export const agentSkillSet = agent
  .table(
    "agent_skill_set",
    {
      agentId: integer("agent_id")
        .notNull()
        .references(() => agents.id, { onDelete: "cascade" }),
      skillSetId: integer("skill_set_id")
        .notNull()
        .references(() => skillSet.id, { onDelete: "cascade" }),
      createdAt: ts("created_at").notNull().defaultNow(),
    },
    (t) => [primaryKey({ columns: [t.agentId, t.skillSetId] })],
  )
  .enableRLS();

/** Which skills a message loaded, so history reconstruction can re-inject them. */
export const messageSkill = agent
  .table(
    "message_skill",
    {
      messageId: integer("message_id")
        .notNull()
        .references(() => messages.id, { onDelete: "cascade" }),
      skillSetId: integer("skill_set_id").notNull(),
      skillName: text("skill_name").notNull(),
    },
    (t) => [
      primaryKey({ columns: [t.messageId, t.skillSetId, t.skillName] }),
      foreignKey({
        columns: [t.skillSetId, t.skillName],
        foreignColumns: [skillSetSkill.skillSetId, skillSetSkill.skillName],
      }).onDelete("cascade"),
      index("message_skill_message_id_idx").on(t.messageId),
      uniqueIndex("message_skill_unique_idx").on(t.messageId, t.skillSetId, t.skillName),
    ],
  )
  .enableRLS();

export type AgentRow = typeof agents.$inferSelect;
export type AgentConfigRow = typeof agentConfig.$inferSelect;
export type ToolSet = typeof toolSet.$inferSelect;
export type ToolSetTool = typeof toolSetTool.$inferSelect;
export type SkillSet = typeof skillSet.$inferSelect;
export type SkillSetSkill = typeof skillSetSkill.$inferSelect;
export type MessageSkill = typeof messageSkill.$inferSelect;
